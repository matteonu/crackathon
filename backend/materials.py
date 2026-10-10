"""User-scoped file library and independent decks; PDF bytes stay in pipeline storage."""
import json
import sqlite3
import time
import uuid

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from auth import current_user
import db
import decks
from errors import RequestError
from material_types import CATEGORY_TYPES, DOCUMENT_TYPES, TYPE_CATEGORIES

bp = Blueprint("materials", __name__, url_prefix="/api/materials")

KINDS = {"folder", "pdf", "md", "txt", "deck"}
CATEGORIES = {"Slides", "Solutions", "Scripts", "Notes", "Transcripts", "Books", "Exams", "Exercises"}
MARKERS = {"To read", "Done", "Revisit", "Ignore"}
MAX_TEXT = 200_000      # a note's content
MAX_JSON = 1_000_000    # outputs or processing, serialised
COLUMNS = ("id, subject_id, parent_id, kind, name, description, category, type, marker, size, "
           "content, added_at, outputs, processing, source_pdf_id, generation_mode, folder_weight")


def jobs():
    # Set by create_app. Asking it for the path keeps one definition of where a PDF lives.
    return current_app.extensions["learning_jobs"]


def to_json(row):
    data = {"id": row["id"], "subjectId": row["subject_id"], "parentId": row["parent_id"],
            "kind": row["kind"], "name": row["name"], "description": row["description"],
            "category": row["category"], "type": row["type"], "marker": row["marker"], "size": row["size"],
            "added": row["added_at"], "sourcePdfId": row["source_pdf_id"],
            "generationMode": row["generation_mode"], "folderWeight": row["folder_weight"]}
    if row["content"] is not None:
        data["content"] = row["content"]
    for key in ("outputs", "processing"):
        if row[key]:
            data[key] = json.loads(row[key])
    if row["kind"] == "deck":
        data["outputs"] = {"flashcards": {"cards": decks.deck_cards(db.get_db(), row["id"])}}
    return data


def classification(body, kind, existing_category=None):
    """Accept stable types or older category-only requests without conflicting flags."""
    document_type = body.get("type")
    if document_type is not None and (not isinstance(document_type, str) or document_type not in DOCUMENT_TYPES):
        raise RequestError(400, "Choose a document type the app offers.")
    category = body.get("category", TYPE_CATEGORIES.get(document_type, existing_category))
    if not isinstance(category, str) or category not in CATEGORIES:
        raise RequestError(400, "Choose a category the app offers.")
    if kind == "folder":
        if document_type is not None:
            raise RequestError(400, "Folders do not have a document type.")
        return category, None
    if "type" not in body:
        document_type = CATEGORY_TYPES.get(category)
    elif (document_type is not None and TYPE_CATEGORIES[document_type] != category
          or document_type is None and category in CATEGORY_TYPES):
        raise RequestError(400, "The document type must match its category.")
    return category, document_type


def valid_name(name, kind):
    if not isinstance(name, str) or not name or len(name) > 180 or name in {".", ".."}:
        return False
    if any(c in name for c in "\\/") or any(ord(c) < 32 for c in name):
        return False
    return kind in {"folder", "deck"} or name.lower().endswith("." + kind)


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
    category, document_type = classification(body, kind)
    if body.get("marker", "To read") not in MARKERS:
        raise RequestError(400, "Choose a marker the app offers.")
    content = body.get("content")
    if kind in {"folder", "pdf", "deck"}:
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
                                          category, type, marker, size, content, added_at, processing)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
          (material_id, user["id"], subject_id, parent_id, kind, name, body.get("description") or "",
           category, document_type, body.get("marker", "To read"), size, content,
           int(time.time() * 1000), as_json_text(body.get("processing"), "processing")))
    return jsonify(to_json(row(material_id))), 201


@bp.get("/<uuid:material_id>")
def detail(material_id):
    return jsonify(to_json(row(str(material_id))))


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
    if "category" in body or "type" in body:
        category, document_type = classification(body, existing["kind"], existing["category"])
        sets += ["category = ?", "type = ?"]
        values += [category, document_type]
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
    if "folderWeight" in body:
        import math
        weight = body["folderWeight"]
        if (existing["kind"] != "folder" or isinstance(weight, bool) or not isinstance(weight, (float, int))
                or not math.isfinite(weight) or weight <= 0):
            raise RequestError(400, "Folder weights must be finite positive numbers.")
        sets.append("folder_weight = ?")
        values.append(weight)
    if "content" in body:
        if existing["kind"] not in {"md", "txt"}:
            raise RequestError(400, "Only text files can be edited.")
        content = body["content"] or ""
        if not isinstance(content, str) or len(content) > MAX_TEXT:
            raise RequestError(400, "This note is too long to save.")
        sets += ["content = ?", "size = ?"]
        values += [content, len(content.encode())]
    outputs = body.get("outputs")
    if outputs is not None and (not isinstance(outputs, dict)
                               or ("flashcards" in outputs and not isinstance(outputs["flashcards"], dict))):
        raise RequestError(400, "Invalid material outputs.")
    for field in ("outputs", "processing"):
        if field in body:
            value = body[field]
            if field == "outputs" and existing["kind"] in {"pdf", "deck"} and value is not None:
                value = {key: val for key, val in value.items() if key != "flashcards"}
            sets.append(f"{field} = ?")
            values.append(as_json_text(value, field))

    with conn:
        if outputs and "flashcards" in outputs:
            cards = outputs["flashcards"].get("cards", [])
            decks.validate_cards(cards)
            if existing["kind"] == "deck":
                decks.replace_cards(conn, material_id, cards)
            elif existing["kind"] == "pdf":
                # Legacy clients can still submit card outputs; content lives only in the deck.
                processing = body.get("processing") or json.loads(existing["processing"] or "{}")
                if processing.get("status") == "complete" and processing.get("task", "flashcards") == "flashcards":
                    generated = [c for c in cards if c.get("generated") or c.get("demo")]
                    deck_id = decks.sync_generated(conn, existing, generated, processing.get("mode", "shallow"))
                    manual = [c for c in cards if not c.get("generated") and not c.get("demo")]
                    saved = decks.deck_cards(conn, deck_id)
                    ids = {c['id'] for c in saved}
                    decks.replace_cards(conn, deck_id, saved + [c for c in manual if c.get('id') not in ids])
        if sets:
            try:
                conn.execute(f"UPDATE materials SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                             values + [material_id, user["id"]])
            except sqlite3.IntegrityError:
                raise RequestError(409, "That material name or relationship is already in use.") from None
    return jsonify(to_json(row(material_id)))


@bp.post("/<uuid:material_id>/cards")
def append_cards(material_id):
    existing = row(str(material_id))
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise RequestError(400, "Provide an object containing the cards.")
    cards = body.get("cards")
    decks.validate_cards(cards)
    if existing["kind"] not in {"deck", "pdf"}:
        raise RequestError(400, "Add cards to a deck or its source PDF.")
    conn = db.get_db()
    with conn:
        deck_id = existing["id"] if existing["kind"] == "deck" else decks.ensure_deck(conn, existing)
        # IDs are assigned by the server for additions.
        decks.replace_cards(conn, deck_id, decks.deck_cards(conn, deck_id) +
                            [{**c, "id": str(uuid.uuid4()), "generated": False, "demo": False} for c in cards])
    return jsonify(to_json(row(deck_id))), 201


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
    current_app.extensions["document_chat"].wake.set()
    # The rows are gone either way; the PDFs and generated results follow.
    for removed_id, kind in removed:
        if kind == "pdf":
            try:
                jobs().delete(removed_id)
            except OSError:
                # Never report a failed logical deletion after committing it, or
                # skip the rest of a deleted folder when one PDF is locked.
                current_app.logger.warning("File cleanup deferred for deleted material %s", removed_id)
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
    current_app.extensions["document_chat"].ensure_index(material_id)
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
