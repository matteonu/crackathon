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

import shutil  # noqa: E402
import sys  # noqa: E402
from urllib.parse import quote  # noqa: E402

import click  # noqa: E402
from flask import Flask, jsonify, send_from_directory  # noqa: E402

import auth  # noqa: E402
from auth import current_user  # noqa: E402
import db  # noqa: E402
import learning  # noqa: E402
import materials  # noqa: E402
import planner  # noqa: E402
import tasks  # noqa: E402
import decks  # noqa: E402
import practice  # noqa: E402
import vvz.sync  # noqa: E402
from learning import RequestError, StudyJobs  # noqa: E402


PUBLIC_URL = "https://13.hackathon.ethz.ch/"
PROXY_SIGN_OUT = "https://auth.hackathon.ethz.ch/oauth2/sign_out?rd=" + quote(PUBLIC_URL, safe="")
DEFAULT_SIGN_OUT_URL = (
    "https://auth.vseth.ethz.ch/auth/realms/VSETH/protocol/openid-connect/logout"
    "?client_id=vis_vc2_prod_portal_oidc&post_logout_redirect_uri=" + quote(PROXY_SIGN_OUT, safe="")
)


def config_from_env():
    data_dir = os.environ.get("DATA_DIR", os.path.join(BACKEND_DIR, "data"))
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "DATA_DIR": data_dir,
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", os.path.join(data_dir, "app.db")),
        # Directories of starting rows, in load order. A later one adds to the earlier
        # ones, which is how dev mode overlays the demo dataset on the production seed.
        "SEED_DIRS": [p for p in os.environ.get(
            "SEED_DIRS", os.path.join(BACKEND_DIR, "seed")).split(os.pathsep) if p],
        # Reseed on every start. Dev mode sets it; on the VM the data must survive a deploy.
        "RESET_DB_ON_START": os.environ.get("RESET_DB_ON_START", "").lower() in {"1", "true", "yes"},
        # Load the seed when there is no database yet, i.e. on the very first start.
        "SEED_IF_NEW": os.environ.get("SEED_IF_NEW", "1").lower() not in {"0", "false", "no"},
        # Stands in for the proxy's X-User-Id when there is no proxy. Never set on the VM.
        "DEV_USER": os.environ.get("DEV_USER", ""),
        "DEV_USER_NAME": os.environ.get("DEV_USER_NAME", ""),
        # Signing out is the login provider's job. This ends the VSETH session at Keycloak
        # and then the proxy's, which hands the browser back to us with no session at all.
        # oauth2-proxy only redirects to *.hackathon.ethz.ch, which is why Keycloak comes
        # first. Set SIGN_OUT_URL to override, or to "" to hide the button.
        "SIGN_OUT_URL": os.environ.get("SIGN_OUT_URL", DEFAULT_SIGN_OUT_URL),
        "LEARNING_DIR": os.environ.get("LEARNING_DIR", os.path.join(data_dir, "learning")),
        "STATIC_DIR": os.environ.get("STATIC_DIR", os.path.join(BACKEND_DIR, "..", "frontend", "dist")),
        # The course catalogue (courses, course_offerings, ...) is filled from the ETH VVZ by a
        # background thread at start and refreshed daily; VVZ_AUTO_SYNC=0 turns that off.
        "VVZ_AUTO_SYNC": os.environ.get("VVZ_AUTO_SYNC", "1").lower() not in {"0", "false", "no"},
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        # 50 MB PDFs, with headroom for the request around them.
        "MAX_CONTENT_LENGTH": 70 * 1024 * 1024,
    }


def _flask_cli():
    """True under `flask --app app <command>`, where a background download would be a nuisance."""
    return os.path.basename(sys.argv[0]) == "flask"


def create_app(overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(config_from_env())
    if overrides:
        app.config.update(overrides)

    db.init_app(app)
    with app.app_context():
        # Whether this is the first start has to be decided before the file is created.
        fresh = not db.exists()
        db.init_db()
        if app.config["RESET_DB_ON_START"] or (fresh and app.config["SEED_IF_NEW"]):
            db.reset_db()
            print(f"Loaded the seed from {os.pathsep.join(app.config['SEED_DIRS'])}", flush=True)

    def save_deck(document_id, result):
        with app.app_context():
            decks.persist_result(db.get_db(), document_id, result)

    app.extensions["learning_jobs"] = StudyJobs(app.config["LEARNING_DIR"], on_complete=save_deck)
    auth.init_app(app)
    app.register_blueprint(materials.bp)
    app.register_blueprint(planner.bp)
    app.register_blueprint(tasks.bp)
    app.register_blueprint(learning.bp)
    app.register_blueprint(practice.bp)
    if app.config["VVZ_AUTO_SYNC"] and not app.testing and not _flask_cli():
        vvz.sync.start_background(app.config["DATABASE_PATH"], app.config["DATA_DIR"])

    @app.errorhandler(RequestError)
    def request_error(exc):
        return jsonify(error=str(exc)), exc.status

    @app.errorhandler(413)
    def too_large(_exc):
        return jsonify(error="The upload is too large (max. 50 MB PDF)."), 413

    @app.get("/api/health")
    def health():
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        user = current_user()
        body = {"email": user["email"], "name": user["display_name"]}
        # Only offer it when there is a proxy session to end: locally there is none.
        if auth.via_proxy() and app.config["SIGN_OUT_URL"]:
            body["signOutUrl"] = app.config["SIGN_OUT_URL"]
        return jsonify(body)

    @app.get("/api/dashboard")
    def dashboard():
        return jsonify(db.get_dashboard(current_user()["id"]))

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        # Serve built Angular files; fall back to index.html for client-side routes.
        # An unknown /api path is a mistake, not a client-side route.
        if path.startswith("api/"):
            return jsonify(error="Unknown endpoint."), 404
        static_dir = app.config["STATIC_DIR"]
        if path and os.path.isfile(os.path.join(static_dir, path)):
            # Some Windows MIME registries call .mjs text/plain, which browsers
            # refuse to load as the PDF renderer's module worker.
            return send_from_directory(static_dir, path, mimetype="text/javascript" if path.endswith(".mjs") else None)
        return send_from_directory(static_dir, "index.html")

    def refill_catalogue():
        """After a reset, put the VVZ courses back from the cached dump (no network, about a second)."""
        if vvz.sync.sync(offline=True, db_path=app.config["DATABASE_PATH"], data_dir=app.config["DATA_DIR"]):
            click.echo("Course catalogue refilled from the cached VVZ dump")
        else:
            click.echo("No cached VVZ dump yet; the catalogue fills when the app next starts")

    @app.cli.command("reset-db")
    def reset_db_command():
        """Delete the database and rebuild it from the seed. Discards everything users changed."""
        db.reset_db()
        click.echo(f"Database reset from {os.pathsep.join(app.config['SEED_DIRS'])}")
        refill_catalogue()

    @app.cli.command("wipe")
    @click.option("--yes", is_flag=True, help="Do not ask.")
    def wipe_command(yes):
        """Clean slate: reload the seed and delete every uploaded PDF and generated result."""
        if not yes:
            click.confirm(f"Delete everything in {app.config['DATA_DIR']}?", abort=True)
        db.reset_db()
        learning_dir = app.config["LEARNING_DIR"]
        removed = 0
        for name in os.listdir(learning_dir) if os.path.isdir(learning_dir) else []:
            shutil.rmtree(os.path.join(learning_dir, name), ignore_errors=True)
            removed += 1
        click.echo(f"Database reloaded from the seed, {removed} uploaded document(s) deleted")
        refill_catalogue()

    @app.cli.command("dump-seed")
    def dump_seed_command():
        """Write the current database into the seed files."""
        for path in db.dump_seed():
            click.echo(f"Wrote {os.path.relpath(path)}")

    return app


if __name__ == "__main__":
    # No proxy locally, so stand in for its headers unless the shell says otherwise.
    app = create_app({"SECRET_KEY": os.environ.get("SECRET_KEY") or "dev-only-secret",
                      "DEV_USER": os.environ.get("DEV_USER") or "alice@ethz.ch",
                      "DEV_USER_NAME": os.environ.get("DEV_USER_NAME") or "Alice Example"})
    # The debug reloader runs this file twice; only announce from the outer process.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        print(f" * Database: {app.config['DATABASE_PATH']}", flush=True)
        key = learning.pdf_study.API_KEY
        print(f" * PDF pipeline: OPENAI_API_KEY {'is set' if key else 'is NOT set (add it to .env)'}, "
              f"model {learning.pdf_study.MODEL}", flush=True)
    app.run(host="0.0.0.0", port=8080, debug=True)
