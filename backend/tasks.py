"""Per-subject to-do lists, scoped to the caller. Like Google Tasks: a task has a title,
optional notes and due date, a priority (high, medium or low), and is open or done. Open
tasks sort by priority and keep a manual order within each priority.

    GET    /api/tasks?subject=<id>      the caller's tasks, optionally one subject
    POST   /api/tasks                   {id, subjectId, title, notes?, due?, priority?, position?}
    PATCH  /api/tasks/<id>              any of title, notes, due, priority, done, position
    DELETE /api/tasks/<id>
    DELETE /api/tasks/completed?subject=<id>   clear the done tasks of one subject
"""
import datetime as dt
import time
import uuid

from flask import Blueprint, jsonify, request

from auth import current_user
import db
from errors import RequestError

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")

MAX_TITLE = 500
MAX_NOTES = 5000
PRIORITIES = ("high", "medium", "low")
COLUMNS = "id, subject_id, title, notes, due, priority, done, completed_at, position, created_at"
# Open tasks: high first, then manual order within a priority.
ORDER = "done, CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, position, created_at DESC"


def to_json(row):
    return {"id": row["id"], "subjectId": row["subject_id"], "title": row["title"], "notes": row["notes"],
            "due": row["due"], "priority": row["priority"], "done": bool(row["done"]), "completedAt": row["completed_at"],
            "position": row["position"], "createdAt": row["created_at"]}


def clean_title(value):
    if not isinstance(value, str):
        raise RequestError(400, "Give the task a title.")
    title = " ".join(value.split())
    if not title or len(title) > MAX_TITLE:
        raise RequestError(400, f"Use a title of 1-{MAX_TITLE} characters.")
    return title


def clean_notes(value):
    notes = value or ""
    if not isinstance(notes, str) or len(notes) > MAX_NOTES:
        raise RequestError(400, "These notes are too long to save.")
    return notes.strip()


def clean_due(value):
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise RequestError(400, "Use a due date like 2026-11-30.") from None


def clean_priority(value):
    if value not in PRIORITIES:
        raise RequestError(400, "Priority must be high, medium or low.")
    return value


def clean_position(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not abs(value) < 1e15:
        raise RequestError(400, "Invalid task position.")
    return float(value)


def row(task_id):
    """One task belonging to the caller, or 404."""
    found = db.get_db().execute(
        f"SELECT {COLUMNS} FROM tasks WHERE id = ? AND user_id = ?", (task_id, current_user()["id"])
    ).fetchone()
    if found is None:
        raise RequestError(404, "This task does not exist.")
    return found


@bp.get("")
def index():
    subject = request.args.get("subject")
    sql = f"SELECT {COLUMNS} FROM tasks WHERE user_id = ?"
    values = [current_user()["id"]]
    if subject:
        sql += " AND subject_id = ?"
        values.append(subject)
    rows = db.get_db().execute(f"{sql} ORDER BY {ORDER}", values)
    return jsonify([to_json(r) for r in rows])


@bp.post("")
def create():
    user = current_user()
    body = request.get_json(silent=True) or {}
    try:
        task_id = str(uuid.UUID(str(body.get("id"))))
    except (ValueError, AttributeError, TypeError):
        raise RequestError(400, "Invalid task ID.") from None
    subject_id = body.get("subjectId")
    if not isinstance(subject_id, str) or not subject_id or len(subject_id) > 100:
        raise RequestError(400, "This task needs a subject.")
    title = clean_title(body.get("title"))
    notes = clean_notes(body.get("notes"))
    due = clean_due(body.get("due"))
    priority = clean_priority(body.get("priority", "medium"))
    conn = db.get_db()
    if "position" in body:
        position = clean_position(body["position"])
    else:
        # New tasks go to the top of the subject's list, as in Google Tasks.
        lowest = conn.execute("SELECT MIN(position) FROM tasks WHERE user_id = ? AND subject_id = ?",
                              (user["id"], subject_id)).fetchone()[0]
        position = (lowest if lowest is not None else 0) - 1
    with conn:
        conn.execute(
            """INSERT INTO tasks (id, user_id, subject_id, title, notes, due, priority, done, completed_at, position, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)""",
            (task_id, user["id"], subject_id, title, notes, due, priority, position, int(time.time() * 1000)))
    return jsonify(to_json(row(task_id))), 201


@bp.patch("/<uuid:task_id>")
def update(task_id):
    task_id = str(task_id)
    row(task_id)
    body = request.get_json(silent=True) or {}
    sets, values = [], []
    if "title" in body:
        sets.append("title = ?")
        values.append(clean_title(body["title"]))
    if "notes" in body:
        sets.append("notes = ?")
        values.append(clean_notes(body["notes"]))
    if "due" in body:
        sets.append("due = ?")
        values.append(clean_due(body["due"]))
    if "priority" in body:
        sets.append("priority = ?")
        values.append(clean_priority(body["priority"]))
    if "done" in body:
        if not isinstance(body["done"], bool):
            raise RequestError(400, "done must be true or false.")
        sets += ["done = ?", "completed_at = ?"]
        values += [int(body["done"]), int(time.time() * 1000) if body["done"] else None]
    if "position" in body:
        sets.append("position = ?")
        values.append(clean_position(body["position"]))
    if sets:
        conn = db.get_db()
        with conn:
            conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                         values + [task_id, current_user()["id"]])
    return jsonify(to_json(row(task_id)))


@bp.delete("/completed")
def clear_completed():
    subject = request.args.get("subject")
    if not subject:
        raise RequestError(400, "Say which subject to clear: ?subject=<id>.")
    conn = db.get_db()
    with conn:
        deleted = conn.execute("DELETE FROM tasks WHERE user_id = ? AND subject_id = ? AND done = 1",
                               (current_user()["id"], subject)).rowcount
    return jsonify(deleted=deleted)


@bp.delete("/<uuid:task_id>")
def delete(task_id):
    task_id = str(task_id)
    row(task_id)
    conn = db.get_db()
    with conn:
        conn.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, current_user()["id"]))
    return "", 204
