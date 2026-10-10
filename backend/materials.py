"""The subject file library: folders, lecture PDFs and text notes, scoped to the caller.

Metadata is in SQLite, PDF bytes are on disk in the pipeline's folder for the same id, so
an upload is stored once and processing reads it from there. `outputs` and `processing` are
kept as the JSON the frontend sends; the server does not read inside them, so the card
shape can change without a migration here.
"""
import json
import sqlite3
import time
import uuid

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from auth import current_user
import db
from errors import RequestError

bp = Blueprint("materials", __name__, url_prefix="/api/materials")

KINDS = {"folder", "pdf", "md", "txt"}
CATEGORIES = {"Slides", "Notes", "Transcripts", "Books", "Exams", "Exercises"}
MARKERS = {"To read", "Done", "Revisit", "Ignore"}
MAX_TEXT = 200_000      # a note's content
MAX_JSON = 1_000_000    # outputs or processing, serialised
COLUMNS = ("id, subject_id, parent_id, kind, name, description, category, marker, size, "
           "content, added_at, outputs, processing")


def jobs():
    # Set by create_app. Asking it for the path keeps one definition of where a PDF lives.
    return current_app.extensions["learning_jobs"]


def to_json(row):
    data = {"id": row["id"], "subjectId": row["subject_id"], "parentId": row["parent_id"],
            "kind": row["kind"], "name": row["name"], "description": row["description"],
            "category": row["category"], "marker": row["marker"], "size": row["size"],
            "added": row["added_at"]}
    if row["content"] is not None:
        data["content"] = row["content"]
    for key in ("outputs", "processing"):
        if row[key]:
            data[key] = json.loads(row[key])
    return data


def valid_name(name, kind):
    if not isinstance(name, str) or not name or len(name) > 180 or name in {".", ".."}:
        return False
    if any(c in name for c in "\\/") or any(ord(c) < 32 for c in name):
        return False
    return kind == "folder" or name.lower().endswith("." + kind)


def as_json_text(value, field):
    if value is None:
        return None
    text = json.dumps(value, ensure_ascii=False)
    if len(text) > MAX_JSON:
        raise RequestError(413, f"The {field} of this file are too large to save.")
    return text


def row(material_id, user_id=None):
    """One material belonging to the caller, or 404."""
    user_id = current_user()["id"] if user_id is None else user_id
    found = db.get_db().execute(
        f"SELECT {COLUMNS}, sha256, user_id FROM materials WHERE id = ? AND user_id = ?",
        (material_id, user_id),
    ).fetchone()
    if found is None:
        raise RequestError(404, "This file does not exist.")
    return found


def owns(material_id):
    """Whether the caller has a material with this id. Used to guard the pipeline routes."""
    return db.get_db().execute(
        "SELECT 1 FROM materials WHERE id = ? AND user_id = ?",
        (material_id, current_user()["id"]),
    ).fetchone() is not None


def subtree(conn, user_id, material_id):
    """The material's id plus every id below it."""
    rows = conn.execute(
        """WITH RECURSIVE tree(id, kind) AS (
               SELECT id, kind FROM materials WHERE id = ? AND user_id = ?
               UNION ALL
               SELECT m.id, m.kind FROM materials m JOIN tree ON m.parent_id = tree.id
           )
           SELECT id, kind FROM tree""",
        (material_id, user_id),
    ).fetchall()
    return [(r["id"], r["kind"]) for r in rows]


def check_parent(conn, user_id, subject_id, parent_id, material_id=None):
    if parent_id is None:
        return
    parent = conn.execute(
        "SELECT kind, subject_id FROM materials WHERE id = ? AND user_id = ?",
        (parent_id, user_id),
    ).fetchone()
    if parent is None or parent["kind"] != "folder" or parent["subject_id"] != subject_id:
        raise RequestError(400, "Choose a folder in this subject.")
    if material_id and parent_id in {child for child, _ in subtree(conn, user_id, material_id)}:
        raise RequestError(400, "A folder cannot contain itself.")


def write(conn, sql, values):
    try:
        with conn:
            return conn.execute(sql, values)
    except sqlite3.IntegrityError as exc:
        if "materials_unique_name" in str(exc):
            raise RequestError(409, "That name already exists in this folder.") from None
        raise RequestError(400, "This file does not fit the data model.") from None


@bp.get("")
def index():
    subject = request.args.get("subject")
    sql = f"SELECT {COLUMNS} FROM materials WHERE user_id = ?"
    values = [current_user()["id"]]
    if subject:
        sql += " AND subject_id = ?"
        values.append(subject)
    rows = db.get_db().execute(sql + " ORDER BY added_at, name", values)
    return jsonify([to_json(r) for r in rows])


@bp.post("")
def create():
    user = current_user()
    body = request.get_json(silent=True) or {}
    kind = body.get("kind")
    if kind not in KINDS:
        raise RequestError(400, "Choose a folder, a PDF or a text file.")
    name = body.get("name", "")
    if not valid_name(name, kind):
        raise RequestError(400, "Use a name of 1-180 characters, without slashes.")
    subject_id = body.get("subjectId")
    if not isinstance(subject_id, str) or not subject_id or len(subject_id) > 100:
        raise RequestError(400, "This file needs a subject.")
    if body.get("category") not in CATEGORIES or body.get("marker", "To read") not in MARKERS:
        raise RequestError(400, "Choose a category and a marker the app offers.")
    content = body.get("content")
    if kind in {"folder", "pdf"}:
        content = None
    elif not isinstance(content, str) or len(content) > MAX_TEXT:
        raise RequestError(400, "This note is too long to save.")
    try:
        material_id = str(uuid.UUID(str(body.get("id"))))
    except (ValueError, AttributeError, TypeError):
        raise RequestError(400, "Invalid file ID.") from None

    conn = db.get_db()
    parent_id = body.get("parentId") or None
    check_parent(conn, user["id"], subject_id, parent_id)
    size = len(content.encode()) if content is not None else int(body.get("size") or 0)
    write(conn, """INSERT INTO materials (id, user_id, subject_id, parent_id, kind, name, description,
                                          category, marker, size, content, added_at, processing)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
          (material_id, user["id"], subject_id, parent_id, kind, name, body.get("description") or "",
           body["category"], body.get("marker", "To read"), size, content,
           int(time.time() * 1000), as_json_text(body.get("processing"), "processing")))
    return jsonify(to_json(row(material_id))), 201


@bp.patch("/<uuid:material_id>")
def update(material_id):
    material_id = str(material_id)
    user = current_user()
    existing = row(material_id)
    body = request.get_json(silent=True) or {}
    conn = db.get_db()
    sets, values = [], []

    if "name" in body:
        if not valid_name(body["name"], existing["kind"]):
            raise RequestError(400, "Use a name of 1-180 characters, without slashes.")
        sets.append("name = ?")
        values.append(body["name"])
    if "description" in body:
        description = body["description"] or ""
        if not isinstance(description, str) or len(description) > 2000:
            raise RequestError(400, "This description is too long.")
        sets.append("description = ?")
        values.append(description)
    if "category" in body:
        if body["category"] not in CATEGORIES:
            raise RequestError(400, "Choose a category the app offers.")
        sets.append("category = ?")
        values.append(body["category"])
    if "marker" in body:
        if body["marker"] not in MARKERS:
            raise RequestError(400, "Choose a marker the app offers.")
        sets.append("marker = ?")
        values.append(body["marker"])
    if "parentId" in body:
        parent_id = body["parentId"] or None
        check_parent(conn, user["id"], existing["subject_id"], parent_id, material_id)
        sets.append("parent_id = ?")
        values.append(parent_id)
    if "content" in body:
        if existing["kind"] not in {"md", "txt"}:
            raise RequestError(400, "Only text files can be edited.")
        content = body["content"] or ""
        if not isinstance(content, str) or len(content) > MAX_TEXT:
            raise RequestError(400, "This note is too long to save.")
        sets += ["content = ?", "size = ?"]
        values += [content, len(content.encode())]
    for field in ("outputs", "processing"):
        if field in body:
            sets.append(f"{field} = ?")
            values.append(as_json_text(body[field], field))

    if sets:
        write(conn, f"UPDATE materials SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
              values + [material_id, user["id"]])
    return jsonify(to_json(row(material_id)))


@bp.delete("/<uuid:material_id>")
def delete(material_id):
    material_id = str(material_id)
    user = current_user()
    conn = db.get_db()
    removed = subtree(conn, user["id"], material_id)
    if not removed:
        raise RequestError(404, "This file does not exist.")
    with conn:
        conn.execute("DELETE FROM materials WHERE id = ? AND user_id = ?", (material_id, user["id"]))
    # The rows are gone either way; the PDFs and generated results follow.
    for removed_id, kind in removed:
        if kind == "pdf":
            jobs().delete(removed_id)
    return jsonify(deleted=[removed_id for removed_id, _ in removed])


@bp.put("/<uuid:material_id>/file")
def upload(material_id):
    material_id = str(material_id)
    existing = row(material_id)
    if existing["kind"] != "pdf":
        raise RequestError(400, "Only a PDF has a file to upload.")
    if (request.content_type or "").split(";", 1)[0] != "application/pdf":
        raise RequestError(415, "Upload the PDF with Content-Type: application/pdf.")
    pdf = request.get_data(cache=False)
    if not pdf or len(pdf) >= 50_000_000:
        raise RequestError(413, "Choose a PDF smaller than 50 MB.")
    if b"%PDF-" not in pdf[:1024]:
        raise RequestError(400, "Choose a valid PDF file.")
    digest = jobs().store_source(material_id, pdf)
    conn = db.get_db()
    with conn:
        conn.execute("UPDATE materials SET size = ?, sha256 = ? WHERE id = ? AND user_id = ?",
                     (len(pdf), digest, material_id, current_user()["id"]))
    return jsonify(to_json(row(material_id)))


@bp.get("/<uuid:material_id>/file")
def download(material_id):
    material_id = str(material_id)
    existing = row(material_id)
    if existing["kind"] in {"md", "txt"}:
        return Response(existing["content"] or "", mimetype="text/plain; charset=utf-8")
    if existing["kind"] != "pdf":
        raise RequestError(400, "A folder has no file.")
    source = jobs().source_path(material_id)
    if not source.exists():
        raise RequestError(404, "This PDF has not been uploaded yet.")
    return send_file(source, mimetype="application/pdf", download_name=existing["name"], max_age=0)
