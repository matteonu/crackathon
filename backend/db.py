"""SQLite access, schema creation and the seed loader.

Paths come from the app config: DATABASE_PATH (the file) and SEED_DIRS (the directories the
starting rows are read from, in order), so tests and dev mode can point at a different
database and a different dataset.
"""
import glob
import json
import os
import sqlite3

from flask import current_app, g

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BACKEND_DIR, "schema.sql")


def init_app(app):
    app.teardown_appcontext(close_db)


def db_path():
    return current_app.config["DATABASE_PATH"]


def seed_dirs():
    return current_app.config["SEED_DIRS"]


def connect(path=None):
    db = sqlite3.connect(path or db_path())
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create every table the schema declares. Existing tables and rows are left alone."""
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    with connect() as db, open(SCHEMA_PATH) as f:
        db.executescript(f.read())


def exists():
    return os.path.exists(db_path())


def seed_files():
    # Files are named NN_<table>.json and loaded in filename order across every seed
    # directory, so tables that others reference must have a lower number. A later
    # directory adds to the earlier ones: production rows plus a demo overlay.
    paths = [p for directory in seed_dirs() for p in glob.glob(os.path.join(directory, "*.json"))]
    for path in sorted(paths, key=os.path.basename):
        table = os.path.basename(path).split("_", 1)[1].removesuffix(".json")
        yield path, table


def reset_db():
    """Delete the database and rebuild it from the seed files."""
    if os.path.exists(db_path()):
        os.remove(db_path())
    init_db()
    with connect() as db:
        for path, table in seed_files():
            with open(path) as f:
                rows = json.load(f)
            for row in rows:
                cols = ", ".join(f'"{c}"' for c in row)
                marks = ", ".join("?" for _ in row)
                db.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})', list(row.values()))


def dump_seed():
    """Write every table back into the seed files. Returns the files written.

    A table keeps the file it was loaded from; a table that has none is written into the
    last seed directory, which is the demo overlay when one is configured.
    """
    out_dir = seed_dirs()[-1]
    os.makedirs(out_dir, exist_ok=True)
    existing = {table: path for path, table in seed_files()}
    next_num = len(existing) + 1
    written = []
    with connect() as db:
        tables = [r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        )]
        for table in tables:
            path = existing.get(table)
            if path is None:
                path = os.path.join(out_dir, f"{next_num:02d}_{table}.json")
                next_num += 1
            rows = [dict(r) for r in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            with open(path, "w") as f:
                json.dump(rows, f, indent=2, ensure_ascii=False)
                f.write("\n")
            written.append(path)
    return written


def get_user_by_id(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_email(email):
    return get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def upsert_user(email, display_name):
    """The user row for this email, created on first sight. Keeps the name the proxy sends."""
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO users (email, display_name) VALUES (?, ?) ON CONFLICT (email) DO NOTHING",
            (email, display_name),
        )
        conn.execute(
            "UPDATE users SET display_name = ? WHERE email = ? AND display_name IS NOT ?",
            (display_name, email, display_name),
        )
    return get_user_by_email(email)


def get_dashboard(user_id):
    """Everything the dashboard shows for one user."""
    conn = get_db()
    user = conn.execute(
        "SELECT email, display_name, birth_date, study_start FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    semesters = [dict(r) for r in conn.execute(
        "SELECT id, label, study_hours_per_week FROM semesters WHERE user_id = ? ORDER BY id",
        (user_id,),
    )]
    for semester in semesters:
        semester["courses"] = [dict(r) for r in conn.execute(
            """SELECT c.id, c.code, c.title, c.term, c.ects, c.professor, sc.desired_grade
               FROM semester_courses sc JOIN courses c ON c.id = sc.course_id
               WHERE sc.semester_id = ? ORDER BY c.code""",
            (semester["id"],),
        )]
        for course in semester["courses"]:
            course["resources"] = [dict(r) for r in conn.execute(
                "SELECT kind, title, url FROM course_resources WHERE course_id = ? ORDER BY id",
                (course["id"],),
            )]
    return {"user": dict(user), "semesters": semesters}
