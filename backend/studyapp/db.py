"""Database infrastructure shared by all features: connection, schema, seed.

Features keep their own queries (e.g. planner/queries.py); this module only
knows how to connect and how to rebuild the database from backend/seed/.
"""
import glob
import json
import os
import sqlite3

import click
from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BACKEND_DIR, "schema.sql")
SEED_DIR = os.path.join(BACKEND_DIR, "seed")


def _path():
    return current_app.config["DATABASE_PATH"]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(_path())
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    with sqlite3.connect(_path()) as db, open(SCHEMA_PATH) as f:
        db.executescript(f.read())


def seed_files():
    # Files are named NN_<table>.json and loaded in filename order,
    # so tables that others reference must have a lower number.
    for path in sorted(glob.glob(os.path.join(SEED_DIR, "*.json"))):
        table = os.path.basename(path).split("_", 1)[1].removesuffix(".json")
        yield path, table


def reset_db():
    """Delete the database and rebuild it from the seed files."""
    if os.path.exists(_path()):
        os.remove(_path())
    init_db()
    with sqlite3.connect(_path()) as db:
        db.execute("PRAGMA foreign_keys = ON")
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
    with sqlite3.connect(_path()) as db:
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


def init_app(app):
    app.teardown_appcontext(close_db)

    @app.cli.command("reset-db")
    def reset_db_command():
        """Delete the database and rebuild it from backend/seed/."""
        reset_db()
        click.echo("Database reset from seed")

    @app.cli.command("dump-seed")
    def dump_seed_command():
        """Write the current database into backend/seed/."""
        for path in dump_seed():
            click.echo(f"Wrote {os.path.relpath(path)}")
