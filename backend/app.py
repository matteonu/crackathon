"""The Studyphase backend: /api/* plus the built Angular app, one process on port 8080.

Run locally with `python backend/app.py`; gunicorn uses `app:create_app()`, the Flask CLI
`--app app`. Settings come from the environment and, locally, from the repo's .env file.
"""
import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env_file(path=os.path.join(BACKEND_DIR, "..", ".env")):
    """Read .env for local runs. Variables already set in the shell win, as on the VM."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


# Must run before the imports below: the pipeline reads OPENAI_API_KEY at import time.
load_env_file()

import click  # noqa: E402
from flask import Flask, jsonify, request, send_from_directory  # noqa: E402
from flask_login import (  # noqa: E402
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash  # noqa: E402

import db  # noqa: E402
import learning  # noqa: E402
from learning import RequestError, StudyJobs  # noqa: E402


def config_from_env():
    data_dir = os.environ.get("DATA_DIR", os.path.join(BACKEND_DIR, "data"))
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "DATA_DIR": data_dir,
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", os.path.join(data_dir, "app.db")),
        "SEED_DIR": os.environ.get("SEED_DIR", os.path.join(BACKEND_DIR, "seed")),
        "LEARNING_DIR": os.environ.get("LEARNING_DIR", os.path.join(data_dir, "learning")),
        "STATIC_DIR": os.environ.get("STATIC_DIR", os.path.join(BACKEND_DIR, "..", "frontend", "dist")),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        # 50 MB PDFs, with headroom for the request around them.
        "MAX_CONTENT_LENGTH": 70 * 1024 * 1024,
    }


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]


def create_app(overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(config_from_env())
    if overrides:
        app.config.update(overrides)

    db.init_app(app)
    with app.app_context():
        db.init_db()

    app.extensions["learning_jobs"] = StudyJobs(app.config["LEARNING_DIR"])
    app.register_blueprint(learning.bp)

    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(user_id):
        row = db.get_user_by_id(user_id)
        return User(row) if row else None

    @login_manager.unauthorized_handler
    def unauthorized():
        # The frontend is a single-page app, so answer with JSON instead of redirecting.
        return jsonify(error="unauthorized"), 401

    @app.errorhandler(RequestError)
    def request_error(exc):
        return jsonify(error=str(exc)), exc.status

    @app.errorhandler(413)
    def too_large(_exc):
        return jsonify(error="The upload is too large (max. 50 MB PDF)."), 413

    @app.get("/api/health")
    def health():
        return jsonify(ok=True)

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

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        # Serve built Angular files; fall back to index.html for client-side routes.
        # An unknown /api path is a mistake, not a client-side route.
        if path.startswith("api/"):
            return jsonify(error="Unknown endpoint."), 404
        static_dir = app.config["STATIC_DIR"]
        if path and os.path.isfile(os.path.join(static_dir, path)):
            return send_from_directory(static_dir, path)
        return send_from_directory(static_dir, "index.html")

    @app.cli.command("reset-db")
    def reset_db_command():
        """Delete the database and rebuild it from the seed directory."""
        db.reset_db()
        click.echo(f"Database reset from {app.config['SEED_DIR']}")

    @app.cli.command("dump-seed")
    def dump_seed_command():
        """Write the current database into the seed directory."""
        for path in db.dump_seed():
            click.echo(f"Wrote {os.path.relpath(path)}")

    return app


if __name__ == "__main__":
    app = create_app({"SECRET_KEY": os.environ.get("SECRET_KEY") or "dev-only-secret"})
    # The debug reloader runs this file twice; only reset in the outer process,
    # so code reloads keep the data you clicked together.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        with app.app_context():
            db.reset_db()
        key = learning.pdf_study.API_KEY
        print(f" * PDF pipeline: OPENAI_API_KEY {'is set' if key else 'is NOT set (add it to .env)'}, "
              f"model {learning.pdf_study.MODEL}", flush=True)
    app.run(host="0.0.0.0", port=8080, debug=True)
