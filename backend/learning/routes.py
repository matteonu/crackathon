"""HTTP layer for the PDF study pipeline, at the same URLs the frontend already calls.

The localhost-only Host/Origin check of the standalone server is gone: this app is reached
through the hackathon reverse proxy, which rejects a request whose Host is localhost.
Access control is the proxy's job (see CLAUDE.md); validation of the upload is still ours.
"""
from __future__ import annotations

from urllib.parse import unquote

from flask import Blueprint, current_app, jsonify, request

from . import pdf_study
from .jobs import SUMMARY_SENTENCES, RequestError

bp = Blueprint("learning", __name__, url_prefix="/api/learning")


def jobs():
    return current_app.extensions["learning_jobs"]


@bp.get("/health")
def health():
    return jsonify(ok=True, keyConfigured=bool(pdf_study.API_KEY.strip()),
                   summarySentences=SUMMARY_SENTENCES, questions=jobs().questions,
                   model=pdf_study.MODEL)


@bp.post("/documents/<uuid:document_id>")
def submit(document_id):
    if (request.content_type or "").split(";", 1)[0] != "application/pdf":
        raise RequestError(415, "Upload the PDF with Content-Type: application/pdf.")
    pdf = request.get_data(cache=False)
    if not 0 < len(pdf) < pdf_study.MAX_PDF_BYTES:
        raise RequestError(413, "Choose a PDF smaller than 50 MB.")
    name = unquote(request.headers.get("X-Filename", "document.pdf"))
    name = name.replace("\\", "/").rsplit("/", 1)[-1][:180]
    mode = request.headers.get("X-Learning-Mode", "shallow")
    try:
        questions = int(request.headers.get("X-Flashcard-Count", str(jobs().questions)))
    except ValueError:
        raise RequestError(400, "Enter a whole number of flashcards from 5 to 300.") from None
    return jsonify(jobs().submit(str(document_id), name, pdf, mode, questions)), 202


@bp.get("/documents/<uuid:document_id>/result.json")
def result(document_id):
    return jsonify(jobs().result(str(document_id), request.args.get("mode", "shallow")))


@bp.delete("/documents/<uuid:document_id>")
def delete(document_id):
    jobs().delete(str(document_id))
    return jsonify(deleted=True)
