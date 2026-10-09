import glob
import json
import os
import sqlite3

from flask import g
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.environ.get(
    "DATABASE_PATH", os.path.join(os.path.dirname(__file__), "data", "app.db")
)
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
SEED_DIR = os.path.join(os.path.dirname(__file__), "seed")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as db, open(SCHEMA_PATH) as f:
        db.executescript(f.read())


def seed_files():
    # Files are named NN_<table>.json and loaded in filename order,
    # so tables that others reference must have a lower number.
    for path in sorted(glob.glob(os.path.join(SEED_DIR, "*.json"))):
        table = os.path.basename(path).split("_", 1)[1].removesuffix(".json")
        yield path, table


def reset_db():
    """Delete the database and rebuild it from the seed files."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    with sqlite3.connect(DB_PATH) as db:
        for path, table in seed_files():
            with open(path) as f:
                rows = json.load(f)
            for row in rows:
                if "password" in row:
                    row["password_hash"] = generate_password_hash(row.pop("password"))
                cols = ", ".join(f'"{c}"' for c in row)
                marks = ", ".join("?" for _ in row)
                db.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})', list(row.values()))


def dump_seed():
    """Write every table back into the seed files. Returns the files written."""
    os.makedirs(SEED_DIR, exist_ok=True)
    existing = {table: path for path, table in seed_files()}
    next_num = len(existing) + 1
    written = []
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        tables = [r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        )]
        for table in tables:
            path = existing.get(table)
            if path is None:
                path = os.path.join(SEED_DIR, f"{next_num:02d}_{table}.json")
                next_num += 1
            rows = [dict(r) for r in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            rows = _keep_plaintext_passwords(path, rows)
            with open(path, "w") as f:
                json.dump(rows, f, indent=2, ensure_ascii=False)
                f.write("\n")
            written.append(path)
    return written


def _keep_plaintext_passwords(path, rows):
    # If the seed already has a plaintext password that still matches, keep it
    # instead of replacing it with the hash, so the seed stays readable.
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        old = {r.get("id"): r for r in json.load(f)}
    for row in rows:
        prev = old.get(row.get("id"), {})
        if "password_hash" in row and "password" in prev and check_password_hash(row["password_hash"], prev["password"]):
            row["password"] = prev["password"]
            del row["password_hash"]
    return rows


def get_user_by_id(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_username(username):
    return get_db().execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
