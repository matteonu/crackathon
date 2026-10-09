import os

import click
from flask import Flask, jsonify, request, send_from_directory
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash

import db

STATIC_DIR = os.environ.get(
    "STATIC_DIR",
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist", "frontend", "browser"),
)

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.teardown_appcontext(db.close_db)
db.init_db()

login_manager = LoginManager(app)


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]


@login_manager.user_loader
def load_user(user_id):
    row = db.get_user_by_id(user_id)
    return User(row) if row else None


@login_manager.unauthorized_handler
def unauthorized():
    # The frontend is a single-page app, so answer with JSON instead of redirecting.
    return jsonify(error="unauthorized"), 401


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    row = db.get_user_by_username(data.get("username", ""))
    if row is None or not check_password_hash(row["password_hash"], data.get("password", "")):
        return jsonify(error="invalid credentials"), 401
    login_user(User(row))
    return jsonify(username=row["username"])


@app.post("/api/logout")
@login_required
def logout():
    logout_user()
    return "", 204


@app.get("/api/me")
@login_required
def me():
    return jsonify(username=current_user.username)


@app.get("/api/dashboard")
@login_required
def dashboard():
    return jsonify(db.get_dashboard(current_user.id))


@app.get("/api/hello")
@login_required
def hello():
    return jsonify(message=f"Hello {current_user.username}, from Flask!")


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def frontend(path):
    # Serve built Angular files; fall back to index.html for client-side routes.
    if path and os.path.isfile(os.path.join(STATIC_DIR, path)):
        return send_from_directory(STATIC_DIR, path)
    return send_from_directory(STATIC_DIR, "index.html")


@app.cli.command("reset-db")
def reset_db_command():
    """Delete the database and rebuild it from backend/seed/."""
    db.reset_db()
    click.echo("Database reset from seed")


@app.cli.command("dump-seed")
def dump_seed_command():
    """Write the current database into backend/seed/."""
    for path in db.dump_seed():
        click.echo(f"Wrote {os.path.relpath(path)}")


if __name__ == "__main__":
    app.secret_key = app.secret_key or "dev-only-secret"
    # The debug reloader runs this file twice; only reset in the outer process,
    # so code reloads keep the data you clicked together.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        db.reset_db()
    app.run(host="0.0.0.0", port=8080, debug=True)
