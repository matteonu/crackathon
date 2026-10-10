"""Background PDF study jobs: one run per (document, mode), results saved as JSON on disk.

The HTTP layer lives in routes.py; the model pipeline lives in pdf_study.py. This module
owns only the job bookkeeping, so the pipeline can be swapped without touching Flask.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import threading
import time

from errors import RequestError

from . import pdf_study

SUMMARY_SENTENCES = 1
DEFAULT_QUESTIONS = 60
DOCUMENT_ID = re.compile(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}")

__all__ = ["DEFAULT_QUESTIONS", "SUMMARY_SENTENCES", "RequestError", "StudyJobs"]


class StudyJobs:
    def __init__(self, directory: Path, questions: int = DEFAULT_QUESTIONS, runner=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.questions = questions
        self.runner = runner or pdf_study.run
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pdf-study")
        self.lock = threading.Lock()
        self.active: set[tuple[str, str]] = set()
        self.deleted: set[str] = set()
        for marker in self.directory.glob("*/.deleted"):
            if DOCUMENT_ID.fullmatch(marker.parent.name):
                self.deletion_marker(marker.parent.name).write_text("deleted", encoding="utf-8")
        for marker in self.directory.glob(".deleted-*"):
            document_id = marker.name.removeprefix(".deleted-")
            if DOCUMENT_ID.fullmatch(document_id):
                self.deleted.add(document_id)
                self.cleanup_deleted(document_id)
        for path in self.directory.rglob("result.json"):
            if self.is_deleted(path.relative_to(self.directory).parts[0]):
                continue
            data = self.read(path)
            if data.get("status") in {"queued", "running"}:
                data.update(status="error", error="Processing was interrupted. Retry to resume saved work.")
                pdf_study.write_json(path, data)

    @staticmethod
    def read(path: Path) -> dict:
        if not path.exists():
            raise RequestError(404, "No result exists for this file yet.")
        data = json.loads(path.read_text(encoding="utf-8"))
        documents = data.get("documents", [])
        data.setdefault("mode", "deep" if documents and documents[0].get("deep_mode") else "shallow")
        data.setdefault("task", "flashcards")
        return data

    def folder(self, document_id: str) -> Path:
        if not DOCUMENT_ID.fullmatch(document_id):
            raise RequestError(400, "Invalid PDF ID.")
        folder = (self.directory / document_id).resolve()
        if folder.parent != self.directory:
            raise RequestError(400, "Invalid PDF storage path.")
        return folder

    def remove_folder(self, document_id: str) -> None:
        # Resolve and verify the exact directory before any recursive removal.
        folder = self.folder(document_id)

        def retry_readonly(function, path, exc_info):
            target = Path(path)
            if not isinstance(exc_info[1], PermissionError) or target.is_symlink() or not target.resolve().is_relative_to(folder):
                raise exc_info[1]
            target.chmod(target.stat().st_mode | stat.S_IWRITE)
            function(path)

        for attempt in range(5):
            try:
                if folder.exists():
                    shutil.rmtree(folder, onerror=retry_readonly)
                return
            except OSError as exc:
                if attempt == 4 or (not isinstance(exc, PermissionError) and getattr(exc, "winerror", None) not in {32, 33, 145}):
                    raise
                time.sleep(.05 * (2 ** attempt))

    def deletion_marker(self, document_id: str) -> Path:
        self.folder(document_id)  # Validate the id and its storage boundary.
        marker = self.directory / f".deleted-{document_id}"
        if marker.is_symlink():
            raise RequestError(400, "Invalid deletion marker.")
        return marker

    def cleanup_deleted(self, document_id: str) -> bool:
        try:
            self.remove_folder(document_id)
            self.deletion_marker(document_id).unlink(missing_ok=True)
            return True
        except OSError:
            # The database row is already gone. Keep a durable marker outside the
            # folder so a locked PDF can be cleaned up after a server restart.
            print(f"PDF cleanup deferred for {document_id}; will retry on restart.", flush=True)
            return False

    def is_deleted(self, document_id: str) -> bool:
        return document_id in self.deleted

    def delete(self, document_id: str) -> None:
        with self.lock:
            folder = self.folder(document_id)
            self.deleted.add(document_id)
            if folder.exists():
                self.deletion_marker(document_id).write_text("deleted", encoding="utf-8")
            if not any(active_id == document_id for active_id, _ in self.active):
                self.cleanup_deleted(document_id)

    def source_path(self, document_id: str) -> Path:
        """Where this document's PDF lives. Uploads write it; the pipeline reads it."""
        return self.folder(document_id) / "source.pdf"

    def store_source(self, document_id: str, pdf: bytes) -> str:
        """Save an uploaded PDF. Returns its digest; refuses to replace a different PDF."""
        digest = hashlib.sha256(pdf).hexdigest()
        with self.lock:
            if self.is_deleted(document_id):
                raise RequestError(410, "This PDF was deleted. Upload it again as a new file.")
            source = self.source_path(document_id)
            if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise RequestError(409, "This file ID belongs to a different PDF. Upload it as a new file.")
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(pdf)
        return digest

    def result_path(self, document_id: str, mode: str, task: str = "flashcards") -> Path:
        if task not in {"summary", "flashcards"}:
            raise RequestError(400, "Choose summary or flashcards.")
        if mode not in {"shallow", "deep"}:
            raise RequestError(400, "Choose shallow or deep processing mode.")
        if task == "summary":
            return self.folder(document_id) / "summary" / mode / "result.json"
        legacy = self.folder(document_id) / "result.json"
        if legacy.exists() and self.read(legacy)["mode"] == mode:
            return legacy
        return self.folder(document_id) / mode / "result.json"

    def result(self, document_id: str, mode: str = "shallow", task: str = "flashcards") -> dict:
        if self.is_deleted(document_id):
            raise RequestError(404, "This PDF was deleted.")
        return self.read(self.result_path(document_id, mode, task))

    def submit(self, document_id: str, name: str, pdf: bytes | None = None, mode: str = "shallow", questions: int | None = None, task: str = "flashcards") -> dict:
        """Start a run. Without `pdf`, the PDF stored for this document is used."""
        questions = self.questions if questions is None else questions
        if task == "summary":
            questions = 0
        elif type(questions) is not int or not 5 <= questions <= 300:
            raise RequestError(400, "Enter a whole number of flashcards from 5 to 300.")
        if mode not in {"shallow", "deep"}:
            raise RequestError(400, "Choose shallow or deep processing mode.")
        if pdf is None:
            stored = self.source_path(document_id)
            if not stored.exists():
                raise RequestError(404, "Upload the PDF before processing it.")
            pdf = stored.read_bytes()
        if not pdf or len(pdf) >= pdf_study.MAX_PDF_BYTES:
            raise RequestError(413, "Choose a PDF smaller than 50 MB.")
        if not name.lower().endswith(".pdf") or b"%PDF-" not in pdf[:1024]:
            raise RequestError(400, "Choose a valid PDF file.")
        digest = hashlib.sha256(pdf).hexdigest()
        with self.lock:
            if self.is_deleted(document_id):
                raise RequestError(410, "This PDF was deleted. Upload it again as a new file.")
            source = self.source_path(document_id)
            output = self.result_path(document_id, mode, task)
            active_key = (document_id, f"{task}:{mode}")
            data = self.read(output) if output.exists() else None
            count_changed = data and data.get("requested_questions", self.questions) != questions
            if (source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() != digest) or (data and data.get("pdf_sha256") != digest):
                raise RequestError(409, "This file ID belongs to a different PDF. Upload it as a new file.")
            if active_key in self.active:
                if count_changed:
                    raise RequestError(409, "Wait for the current generation to finish before changing the count.")
                return data
            if data and data.get("status") == "complete" and not count_changed:
                return data
            if not pdf_study.API_KEY.strip():
                raise RequestError(503, "The model API key is missing. Set OPENAI_API_KEY in .env and restart the server, then retry.")
            output.parent.mkdir(parents=True, exist_ok=True)
            if not source.exists():
                source.write_bytes(pdf)
            if data is None or count_changed:
                documents = []
                # Reuse the upload summary; generating cards must not erase it or
                # spend another request on the same abstract.
                if task == "flashcards":
                    for summary_mode in (mode, "deep", "shallow"):
                        summary_path = self.result_path(document_id, summary_mode, "summary")
                        if summary_path.exists():
                            summary = self.read(summary_path)
                            if summary.get("status") == "complete" and summary.get("documents"):
                                document = dict(summary["documents"][0])
                                document.update(deep_mode=mode == "deep", complete=False, questions=[], requested_questions=questions)
                                documents = [document]
                                break
                data = {"id": document_id, "file": name, "pdf_sha256": digest, "mode": mode, "task": task,
                        "requested_sentences": SUMMARY_SENTENCES, "requested_questions": questions,
                        "documents": documents}
            data.update(status="queued", error="")
            pdf_study.write_json(output, data)
            self.active.add(active_key)
            self.pool.submit(self.process, document_id, source, output, mode, task)
            return data

    def process(self, document_id: str, source: Path, output: Path, mode: str, task: str) -> None:
        try:
            if self.is_deleted(document_id):
                return
            data = self.read(output)
            data.update(status="running", error="")
            pdf_study.write_json(output, data)
            args = argparse.Namespace(pdfs=[str(source)], output=str(output),
                                      sentences=data["requested_sentences"], questions=data["requested_questions"],
                                      language="same language as the PDF", model=pdf_study.MODEL,
                                      timeout=600, allow_empty_pages=False, feedback="", deep_mode=mode == "deep",
                                      cancelled=lambda: self.is_deleted(document_id), task=task)
            self.runner(args)
            if self.is_deleted(document_id):
                return
            data = self.read(output)
            if not data["documents"] or not data["documents"][0].get("complete"):
                raise pdf_study.WorkflowError("Processing did not finish. Retry to resume saved work.")
            data.update(status="complete", error="")
            pdf_study.write_json(output, data)
        except Exception as exc:
            if self.is_deleted(document_id):
                return
            # Only the pipeline's sanitized actionable errors can be sent to the browser.
            message = str(exc) if isinstance(exc, pdf_study.WorkflowError) else "Processing failed. Retry to resume saved work."
            try:
                data = self.read(output)
                data.update(status="error", error=message)
                pdf_study.write_json(output, data)
            finally:
                print(f"PDF job {document_id}: {message}", flush=True)
        finally:
            with self.lock:
                self.active.discard((document_id, f"{task}:{mode}"))
                if self.is_deleted(document_id) and not any(active_id == document_id for active_id, _ in self.active):
                    self.cleanup_deleted(document_id)
