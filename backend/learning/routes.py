"""HTTP layer for the PDF study pipeline, at the same URLs the frontend already calls.

The localhost-only Host/Origin check of the standalone server is gone: this app is reached
through the hackathon reverse proxy, which rejects a request whose Host is localhost.
Access control is the proxy's job (see CLAUDE.md); validation of the upload is still ours.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from urllib.parse import unquote

from flask import Blueprint, current_app, jsonify, request

from auth import current_user
import db
import materials
from material_types import FLASHCARD_TYPES

from . import pdf_study
from .config import MODELS
from .jobs import SUMMARY_SENTENCES, RequestError

bp = Blueprint("learning", __name__, url_prefix="/api/learning")


def jobs():
    return current_app.extensions["learning_jobs"]


def mcq_jobs():
    return current_app.extensions["mcq_jobs"]


def owned(document_id):
    """A document is a material of the caller's. Ids are uuids, but obscurity is not access."""
    document_id = str(document_id)
    if not materials.owns(document_id):
        raise RequestError(404, "This file does not exist.")
    return document_id


@bp.get("/health")
def health():
    return jsonify(ok=True, keyConfigured=bool(pdf_study.API_KEY.strip()),
                   summarySentences=SUMMARY_SENTENCES, questions=jobs().questions,
                   model=pdf_study.MODEL, summaryModel=pdf_study.SUMMARY_MODEL,
                   models=MODELS)


@bp.post("/documents/<uuid:document_id>")
def submit(document_id):
    document_id = owned(document_id)
    # The PDF is already stored by the upload, so a body is optional.
    pdf = None
    if request.content_length:
        if (request.content_type or "").split(";", 1)[0] != "application/pdf":
            raise RequestError(415, "Upload the PDF with Content-Type: application/pdf.")
        pdf = request.get_data(cache=False)
        if not 0 < len(pdf) < pdf_study.MAX_PDF_BYTES:
            raise RequestError(413, "Choose a PDF smaller than 50 MB.")
    name = unquote(request.headers.get("X-Filename", "document.pdf"))
    name = name.replace("\\", "/").rsplit("/", 1)[-1][:180]
    mode = request.headers.get("X-Learning-Mode", "shallow")
    task = request.headers.get("X-Learning-Task", "flashcards")
    if task not in {"summary", "flashcards"}:
        raise RequestError(400, "Choose summary or flashcards.")
    material = materials.row(document_id)
    if material["kind"] != "pdf":
        raise RequestError(400, "Choose a PDF to process.")
    if task == "flashcards" and material["type"] not in FLASHCARD_TYPES:
        raise RequestError(400, "Flashcards are available for slides, solutions and scripts.")
    try:
        questions = int(request.headers.get("X-Flashcard-Count", str(jobs().questions)))
    except ValueError:
        raise RequestError(400, "Enter a whole number of flashcards from 5 to 300.") from None
    result = jobs().submit(document_id, name, pdf, mode, questions, task)
    if pdf is not None:
        current_app.extensions['document_chat'].ensure_index(document_id)
    return jsonify(result), 202


@bp.get("/documents/<uuid:document_id>/result.json")
def result(document_id):
    return jsonify(jobs().result(owned(document_id), request.args.get("mode", "shallow"), request.args.get("task", "flashcards")))


@bp.delete("/documents/<uuid:document_id>")
def delete(document_id):
    document_id = owned(document_id)
    current_app.extensions["document_chat"].delete_context(document_id)
    jobs().delete(document_id)
    return jsonify(deleted=True)


def owned_set(set_id, complete=False):
    row = db.get_db().execute(
        "SELECT * FROM mcq_sets WHERE id=? AND user_id=?", (str(set_id), current_user()["id"])
    ).fetchone()
    if row is None:
        raise RequestError(404, "This MC question set does not exist.")
    if complete and row["status"] != "complete":
        raise RequestError(409, "This MC question set is not ready yet.")
    return row


def set_json(row, include_questions=False):
    conn = db.get_db()
    body = {"id": row["id"], "documentId": row["material_id"], "mode": row["mode"],
            "seriesId": row["series_id"], "version": row["version"], "status": row["status"],
            "requestedQuestionCount": row["requested_count"],
            "replacesId": row["replaces_id"], "supersededById": row["superseded_by_id"],
            "error": row["error"], "createdAt": row["created_at"], "completedAt": row["completed_at"]}
    body["questionCount"] = conn.execute("SELECT count(*) FROM mcq_questions WHERE set_id=?", (row["id"],)).fetchone()[0]
    latest = conn.execute("""SELECT score, (SELECT count(*) FROM mcq_questions WHERE set_id=s.set_id) total
                             FROM mcq_sessions s WHERE set_id=? AND user_id=? AND status='completed'
                             ORDER BY completed_at DESC, rowid DESC LIMIT 1""", (row["id"], current_user()["id"])).fetchone()
    body["latestScore"] = ({"correct": latest["score"], "total": latest["total"]} if latest else None)
    active = conn.execute("SELECT id FROM mcq_sessions WHERE set_id=? AND user_id=? AND status='active'",
                          (row["id"], current_user()["id"])).fetchone()
    body["activeSessionId"] = active["id"] if active else None
    if include_questions and row["status"] == "complete":
        body["questions"] = questions_json(row["id"])
    return body


def questions_json(set_id):
    conn = db.get_db(); result = []
    for q in conn.execute("SELECT * FROM mcq_questions WHERE set_id=? ORDER BY position", (set_id,)):
        result.append({"id": q["id"], "prompt": q["prompt"], "selectionMode": q["selection_mode"],
                       "options": [{"id": o["id"], "text": o["text"]} for o in conn.execute(
                           "SELECT id,text FROM mcq_options WHERE question_id=? ORDER BY position", (q["id"],))]})
    return result


@bp.route("/documents/<uuid:document_id>/mcq-sets", methods=["GET", "POST"])
def document_mcq_sets(document_id):
    document_id = owned(document_id)
    material = materials.row(document_id)
    if material["kind"] != "pdf" or material["category"] not in {"Slides", "Scripts"}:
        raise RequestError(400, "MC questions are available for Slides and Scripts PDFs.")
    conn = db.get_db(); user_id = current_user()["id"]
    if request.method == "GET":
        rows = conn.execute("""SELECT * FROM mcq_sets s WHERE material_id=? AND s.user_id=?
                               AND (superseded_by_id IS NULL OR EXISTS (
                                 SELECT 1 FROM mcq_sessions x WHERE x.set_id=s.id AND x.user_id=s.user_id AND x.status='active'))
                               ORDER BY created_at DESC, version DESC""", (document_id, user_id))
        return jsonify([set_json(row) for row in rows])
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "shallow")
    if mode not in {"shallow", "deep"}:
        raise RequestError(400, "Choose shallow or deep mode.")
    key = body.get("idempotencyKey")
    if not isinstance(key, str) or not key.strip() or len(key) > 200:
        raise RequestError(400, "Provide an idempotency key.")
    requested_count = body.get("questionCount")
    if requested_count is not None and (type(requested_count) is not int or not 1 <= requested_count <= 60):
        raise RequestError(400, "Enter a whole number of MC questions from 1 to 60, or leave it empty.")
    previous = conn.execute("SELECT * FROM mcq_sets WHERE user_id=? AND idempotency_key=?", (user_id, key)).fetchone()
    if previous:
        return jsonify(set_json(previous)), 200
    action = body.get("action", "initial")
    replaces = None
    if action == "regenerate":
        target = body.get("setId")
        replaces = owned_set(target, True)
        if replaces["material_id"] != document_id:
            raise RequestError(400, "Regenerate a set from this PDF.")
        series_id = replaces["series_id"]
        version = conn.execute("SELECT max(version)+1 FROM mcq_sets WHERE series_id=?", (series_id,)).fetchone()[0]
    elif action in {"initial", "additional"}:
        if action == "initial" and conn.execute("SELECT 1 FROM mcq_sets WHERE material_id=?", (document_id,)).fetchone():
            action = "additional"
        series_id = str(uuid.uuid4()); version = 1
    else:
        raise RequestError(400, "Choose initial, additional or regenerate.")
    set_id = str(uuid.uuid4())
    try:
        with conn:
            conn.execute("""INSERT INTO mcq_sets
                (id,material_id,user_id,mode,series_id,version,status,requested_count,replaces_id,idempotency_key)
                VALUES (?,?,?,?,?,?,'queued',?,?,?)""",
                (set_id, document_id, user_id, mode, series_id, version, requested_count,
                 replaces["id"] if replaces else None, key))
    except sqlite3.IntegrityError:
        active = conn.execute("SELECT * FROM mcq_sets WHERE material_id=? AND status IN ('queued','running')", (document_id,)).fetchone()
        if active: raise RequestError(409, "MC question generation is already in progress for this PDF.") from None
        raise
    mcq_jobs().submit(set_id)
    return jsonify(set_json(conn.execute("SELECT * FROM mcq_sets WHERE id=?", (set_id,)).fetchone())), 202


@bp.get("/mcq-sets/<uuid:set_id>")
def mcq_set_detail(set_id):
    row = owned_set(set_id)
    return jsonify(set_json(row, include_questions=True))


@bp.post("/mcq-sets/<uuid:set_id>/retry")
def retry_mcq_set(set_id):
    row = owned_set(set_id)
    if row["status"] != "error": raise RequestError(409, "Only a failed generation can be retried.")
    conn = db.get_db()
    try:
        with conn: conn.execute("UPDATE mcq_sets SET status='queued', error=NULL WHERE id=?", (row["id"],))
    except sqlite3.IntegrityError:
        raise RequestError(409, "MC question generation is already in progress for this PDF.") from None
    mcq_jobs().submit(row["id"])
    return jsonify(set_json(conn.execute("SELECT * FROM mcq_sets WHERE id=?", (row["id"],)).fetchone())), 202


@bp.post("/mcq-sets/<uuid:set_id>/sessions")
def start_mcq_session(set_id):
    row = owned_set(set_id, True); conn = db.get_db(); user_id = current_user()["id"]
    active = conn.execute("SELECT * FROM mcq_sessions WHERE set_id=? AND user_id=? AND status='active'", (row["id"], user_id)).fetchone()
    if active: return jsonify(session_json(active)), 200
    session_id = str(uuid.uuid4())
    with conn: conn.execute("INSERT INTO mcq_sessions (id,set_id,user_id,status) VALUES (?,?,?,'active')", (session_id, row["id"], user_id))
    return jsonify(session_json(conn.execute("SELECT * FROM mcq_sessions WHERE id=?", (session_id,)).fetchone())), 201


def owned_session(session_id):
    row = db.get_db().execute("SELECT * FROM mcq_sessions WHERE id=? AND user_id=?", (str(session_id), current_user()["id"])).fetchone()
    if row is None: raise RequestError(404, "This practice session does not exist.")
    return row


def session_json(row):
    total = db.get_db().execute("SELECT count(*) FROM mcq_questions WHERE set_id=?", (row["set_id"],)).fetchone()[0]
    return {"id": row["id"], "setId": row["set_id"], "status": row["status"], "position": row["position"],
            "score": row["score"], "total": total, "questions": questions_json(row["set_id"])}


@bp.get("/mcq-sessions/<uuid:session_id>")
def mcq_session_detail(session_id):
    return jsonify(session_json(owned_session(session_id)))


@bp.post("/mcq-sessions/<uuid:session_id>/answers")
def answer_mcq(session_id):
    session = owned_session(session_id); conn = db.get_db()
    body = request.get_json(silent=True) or {}; question_id = str(body.get("questionId", ""))
    selected = body.get("selectedOptionIds")
    if not isinstance(selected, list) or not selected or any(not isinstance(x, str) for x in selected) or len(selected) != len(set(selected)):
        raise RequestError(400, "Select one or more answer options.")
    question = conn.execute("SELECT * FROM mcq_questions WHERE id=? AND set_id=?", (question_id, session["set_id"])).fetchone()
    if question is None: raise RequestError(400, "Choose a question in this session.")
    existing = conn.execute("SELECT * FROM mcq_session_answers WHERE session_id=? AND question_id=?", (session["id"], question_id)).fetchone()
    canonical = json.dumps(sorted(selected))
    if existing:
        if existing["selected_option_ids"] != canonical: raise RequestError(409, "This question already has a different answer.")
        correct = bool(existing["is_correct"])
    else:
        if session["status"] != "active": raise RequestError(409, "This practice session is already complete.")
        expected_question = conn.execute("SELECT id FROM mcq_questions WHERE set_id=? AND position=?", (session["set_id"], session["position"])).fetchone()
        if expected_question is None or expected_question["id"] != question_id: raise RequestError(409, "Answer the current question first.")
        option_rows = conn.execute("SELECT id,is_correct FROM mcq_options WHERE question_id=?", (question_id,)).fetchall()
        valid = {o["id"] for o in option_rows}
        if any(x not in valid for x in selected): raise RequestError(400, "Choose options from this question.")
        correct_ids = {o["id"] for o in option_rows if o["is_correct"]}
        correct = set(selected) == correct_ids
        total = conn.execute("SELECT count(*) FROM mcq_questions WHERE set_id=?", (session["set_id"],)).fetchone()[0]
        next_position = session["position"] + 1; completed = next_position >= total
        with conn:
            conn.execute("INSERT INTO mcq_session_answers VALUES (?,?,?,?,datetime('now'))", (session["id"], question_id, canonical, int(correct)))
            conn.execute("""UPDATE mcq_sessions SET position=?, score=score+?, status=?,
                            completed_at=CASE WHEN ? THEN datetime('now') ELSE NULL END WHERE id=?""",
                         (next_position, int(correct), "completed" if completed else "active", int(completed), session["id"]))
    correct_ids = [r["id"] for r in conn.execute("SELECT id FROM mcq_options WHERE question_id=? AND is_correct=1 ORDER BY position", (question_id,))]
    pages = [r["page"] for r in conn.execute("SELECT page FROM mcq_question_pages WHERE question_id=? ORDER BY page", (question_id,))]
    updated = conn.execute("SELECT * FROM mcq_sessions WHERE id=?", (session["id"],)).fetchone()
    return jsonify({"correct": correct, "correctOptionIds": correct_ids, "explanation": question["explanation"],
                    "sourcePages": pages, "session": session_json(updated)})
