"""Local PDF study pipeline and the built learning frontend, served on one origin."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import parse_qs, unquote, urlsplit

from . import pdf_study

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SENTENCES = 1
DEFAULT_QUESTIONS = 60
DOCUMENT_ROUTE = re.compile(r"/api/learning/documents/([a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12})(/result\.json)?$")


class RequestError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


class StudyJobs:
    def __init__(self, directory: Path, questions: int = DEFAULT_QUESTIONS, runner=None):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.questions = questions
        self.runner = runner or pdf_study.run
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pdf-study")
        self.lock = threading.Lock()
        self.active: set[tuple[str, str]] = set()
        self.deleted: set[str] = set()
        for marker in self.directory.glob('*/.deleted'):
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
        if not DOCUMENT_ROUTE.fullmatch('/api/learning/documents/' + document_id):
            raise RequestError(400, 'Invalid PDF ID.')
        folder = (self.directory / document_id).resolve()
        if folder.parent != self.directory:
            raise RequestError(400, 'Invalid PDF storage path.')
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
                (folder / '.deleted').write_text('deleted', encoding='utf-8')
            if not any(active_id == document_id for active_id, _ in self.active):
                self.remove_folder(document_id)

    def result_path(self, document_id: str, mode: str) -> Path:
        if mode not in {"shallow", "deep"}:
            raise RequestError(400, "Choose shallow or deep processing mode.")
        legacy = self.folder(document_id) / "result.json"
        if legacy.exists() and self.read(legacy)["mode"] == mode:
            return legacy
        return self.folder(document_id) / mode / "result.json"

    def result(self, document_id: str, mode: str = "shallow") -> dict:
        if self.is_deleted(document_id):
            raise RequestError(404, 'This PDF was deleted.')
        return self.read(self.result_path(document_id, mode))

    def submit(self, document_id: str, name: str, pdf: bytes, mode: str = "shallow", questions: int | None = None) -> dict:
        questions = self.questions if questions is None else questions
        if type(questions) is not int or not 5 <= questions <= 300:
            raise RequestError(400, 'Enter a whole number of flashcards from 5 to 300.')
        if mode not in {"shallow", "deep"}:
            raise RequestError(400, "Choose shallow or deep processing mode.")
        if not pdf or len(pdf) >= pdf_study.MAX_PDF_BYTES:
            raise RequestError(413, "Choose a PDF smaller than 50 MB.")
        if not name.lower().endswith(".pdf") or b"%PDF-" not in pdf[:1024]:
            raise RequestError(400, "Choose a valid PDF file.")
        digest = hashlib.sha256(pdf).hexdigest()
        with self.lock:
            if self.is_deleted(document_id):
                raise RequestError(410, 'This PDF was deleted. Upload it again as a new file.')
            folder = self.folder(document_id)
            source = folder / "source.pdf"
            output = self.result_path(document_id, mode)
            data = self.read(output) if output.exists() else None
            if data and data.get('requested_questions', self.questions) != questions:
                raise RequestError(409, 'This upload uses a different flashcard count. Upload it again to change the count.')
            if (source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() != digest) or (data and data.get("pdf_sha256") != digest):
                raise RequestError(409, "This file ID belongs to a different PDF. Upload it as a new file.")
            if data and ((document_id, mode) in self.active or data.get("status") == "complete"):
                return data
            if not pdf_study.API_KEY.strip():
                raise RequestError(503, "Set OPENAI_API_KEY in the Python server's terminal and restart it, then retry.")
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


def create_server(jobs: StudyJobs, port: int = 8010, static_dir: Path | None = None) -> ThreadingHTTPServer:
    static_root = (static_dir or ROOT / "frontend" / "dist").resolve()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status: int, payload: dict) -> None:
            self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def send_bytes(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def check_local_request(self) -> None:
            if urlsplit("http://" + self.headers.get("Host", "")).hostname not in {"localhost", "127.0.0.1"}:
                raise RequestError(403, "This server is available only on localhost.")
            origin = self.headers.get("Origin")
            if origin:
                allowed = {f"http://{host}:{p}" for host in ("localhost", "127.0.0.1")
                           for p in (self.server.server_port, 4300)}
                if origin not in allowed:
                    raise RequestError(403, "Open the local learning view before uploading.")

        def do_POST(self) -> None:
            try:
                self.check_local_request()
                match = DOCUMENT_ROUTE.fullmatch(urlsplit(self.path).path)
                if not match or match[2]:
                    raise RequestError(404, "Unknown endpoint.")
                if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/pdf":
                    raise RequestError(415, "Upload the PDF with Content-Type: application/pdf.")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise RequestError(400, "Invalid upload size.") from None
                if not 0 < length < pdf_study.MAX_PDF_BYTES:
                    raise RequestError(413, "Choose a PDF smaller than 50 MB.")
                name = unquote(self.headers.get("X-Filename", "document.pdf"))
                name = name.replace("\\", "/").rsplit("/", 1)[-1][:180]
                pdf = self.rfile.read(length)
                if len(pdf) != length:
                    raise RequestError(400, "Upload was interrupted. Retry the file.")
                mode = self.headers.get("X-Learning-Mode", "shallow")
                try:
                    questions = int(self.headers.get('X-Flashcard-Count', str(jobs.questions)))
                except ValueError:
                    raise RequestError(400, 'Enter a whole number of flashcards from 5 to 300.') from None
                self.send_json(202, jobs.submit(match[1], name, pdf, mode, questions))
            except RequestError as exc:
                self.send_json(exc.status, {"error": str(exc)})
            except (OSError, ValueError):
                self.send_json(500, {"error": "Could not save the PDF or read its results. Check server storage."})

        def do_DELETE(self) -> None:
            try:
                self.check_local_request()
                match = DOCUMENT_ROUTE.fullmatch(urlsplit(self.path).path)
                if not match or match[2]:
                    raise RequestError(404, 'Unknown endpoint.')
                jobs.delete(match[1])
                self.send_json(200, {'deleted': True})
            except RequestError as exc:
                self.send_json(exc.status, {'error': str(exc)})
            except OSError:
                self.send_json(500, {'error': 'Could not delete the PDF. Please retry.'})

        def do_GET(self) -> None:
            try:
                self.check_local_request()
                path = urlsplit(self.path).path
                if path == "/api/learning/health":
                    self.send_json(200, {"ok": True, "keyConfigured": bool(pdf_study.API_KEY.strip()),
                                         "summarySentences": SUMMARY_SENTENCES, "questions": jobs.questions,
                                         "model": pdf_study.MODEL})
                    return
                match = DOCUMENT_ROUTE.fullmatch(path)
                if match and match[2]:
                    mode = parse_qs(urlsplit(self.path).query).get("mode", ["shallow"])[0]
                    self.send_json(200, jobs.result(match[1], mode))
                    return
                if path.startswith("/api/"):
                    raise RequestError(404, "Unknown endpoint.")
                target = (static_root / unquote(path).lstrip("/")).resolve()
                if not target.is_relative_to(static_root):
                    raise RequestError(404, "File not found.")
                if path == "/":
                    target = static_root / "index.html"
                if not target.is_file():
                    raise RequestError(404, "Frontend file not found. Run npm run build in frontend first.")
                content_type = {".js": "application/javascript", ".mjs": "application/javascript",
                                ".css": "text/css", ".wasm": "application/wasm"}.get(target.suffix)
                self.send_bytes(200, target.read_bytes(), content_type or mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            except RequestError as exc:
                self.send_json(exc.status, {"error": str(exc)})
            except (OSError, ValueError):
                self.send_json(500, {"error": "Could not read saved results. Retry after checking server storage."})

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "learning_backend" / "data")
    parser.add_argument("--questions", type=int, default=DEFAULT_QUESTIONS)
    args = parser.parse_args()
    if not 5 <= args.questions <= 300:
        parser.error("--questions must be between 5 and 300.")
    jobs = StudyJobs(args.data_dir, args.questions)
    server = create_server(jobs, args.port)
    print(f"Learning view: http://127.0.0.1:{server.server_port}", flush=True)
    if not pdf_study.API_KEY.strip():
        print("Set OPENAI_API_KEY and restart this server to enable PDF generation.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        jobs.pool.shutdown(wait=True)


if __name__ == "__main__":
    main()
