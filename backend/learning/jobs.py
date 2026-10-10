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
import threading

from . import pdf_study

SUMMARY_SENTENCES = 1
DEFAULT_QUESTIONS = 60
DOCUMENT_ID = re.compile(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}")


class RequestError(Exception):
    """An error with a status code and a message that is safe to show the user."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


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
            self.deleted.add(marker.parent.name)
            self.remove_folder(marker.parent.name)
        for path in self.directory.rglob("result.json"):
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
        if folder.exists():
            shutil.rmtree(folder)

    def is_deleted(self, document_id: str) -> bool:
        return document_id in self.deleted

    def delete(self, document_id: str) -> None:
        with self.lock:
            folder = self.folder(document_id)
            self.deleted.add(document_id)
            if folder.exists():
                (folder / ".deleted").write_text("deleted", encoding="utf-8")
            if not any(active_id == document_id for active_id, _ in self.active):
                self.remove_folder(document_id)

    def source_path(self, document_id: str) -> Path:
        return self.folder(document_id) / "source.pdf"

    def result_path(self, document_id: str, mode: str) -> Path:
        if mode not in {"shallow", "deep"}:
            raise RequestError(400, "Choose shallow or deep processing mode.")
        legacy = self.folder(document_id) / "result.json"
        if legacy.exists() and self.read(legacy)["mode"] == mode:
            return legacy
        return self.folder(document_id) / mode / "result.json"

    def result(self, document_id: str, mode: str = "shallow") -> dict:
        if self.is_deleted(document_id):
            raise RequestError(404, "This PDF was deleted.")
        return self.read(self.result_path(document_id, mode))

    def submit(self, document_id: str, name: str, pdf: bytes, mode: str = "shallow", questions: int | None = None) -> dict:
        questions = self.questions if questions is None else questions
        if type(questions) is not int or not 5 <= questions <= 300:
            raise RequestError(400, "Enter a whole number of flashcards from 5 to 300.")
        if mode not in {"shallow", "deep"}:
            raise RequestError(400, "Choose shallow or deep processing mode.")
        if not pdf or len(pdf) >= pdf_study.MAX_PDF_BYTES:
            raise RequestError(413, "Choose a PDF smaller than 50 MB.")
        if not name.lower().endswith(".pdf") or b"%PDF-" not in pdf[:1024]:
            raise RequestError(400, "Choose a valid PDF file.")
        digest = hashlib.sha256(pdf).hexdigest()
        with self.lock:
            if self.is_deleted(document_id):
                raise RequestError(410, "This PDF was deleted. Upload it again as a new file.")
            source = self.source_path(document_id)
            output = self.result_path(document_id, mode)
            data = self.read(output) if output.exists() else None
            if data and data.get("requested_questions", self.questions) != questions:
                raise RequestError(409, "This upload uses a different flashcard count. Upload it again to change the count.")
            if (source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() != digest) or (data and data.get("pdf_sha256") != digest):
                raise RequestError(409, "This file ID belongs to a different PDF. Upload it as a new file.")
            if data and ((document_id, mode) in self.active or data.get("status") == "complete"):
                return data
            if not pdf_study.API_KEY.strip():
                raise RequestError(503, "The model API key is missing. Set OPENAI_API_KEY in .env and restart the server, then retry.")
            output.parent.mkdir(parents=True, exist_ok=True)
            if not source.exists():
                source.write_bytes(pdf)
            if data is None:
                data = {"id": document_id, "file": name, "pdf_sha256": digest, "mode": mode,
                        "requested_sentences": SUMMARY_SENTENCES, "requested_questions": questions,
                        "documents": []}
            data.update(status="queued", error="")
            pdf_study.write_json(output, data)
            self.active.add((document_id, mode))
            self.pool.submit(self.process, document_id, source, output, mode)
            return data

    def process(self, document_id: str, source: Path, output: Path, mode: str) -> None:
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
                                      cancelled=lambda: self.is_deleted(document_id))
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
                self.active.discard((document_id, mode))
                if self.is_deleted(document_id) and not any(active_id == document_id for active_id, _ in self.active):
                    self.remove_folder(document_id)
