import os
import base64
import binascii

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

try:
    import db
except ModuleNotFoundError:
    from . import db
try:  # Supports both `flask --app backend/app.py` and `import backend.app`.
    from document_engine.engine import DocumentEngine, EngineError
    from document_engine.models import Card, ProcessingMode
except ModuleNotFoundError:
    from .document_engine.engine import DocumentEngine, EngineError
    from .document_engine.models import Card, ProcessingMode

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
document_engine = DocumentEngine()


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


def _document_payload():
    data = request.get_json(silent=True) or {}
    encoded = data.get("pdfBase64", "")
    if not isinstance(encoded, str):
        raise EngineError("pdfBase64 must be a base64-encoded PDF.")
    if encoded.startswith("data:"):
        encoded = encoded.split(",", 1)[-1]
    try:
        pdf_data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EngineError("pdfBase64 must be a base64-encoded PDF.") from exc
    mode = ProcessingMode(data.get("mode", ProcessingMode.QUICK.value))
    return data, pdf_data, mode


def _cards_json(cards: list[Card]):
    return [{"front": card.front, "back": card.back, "type": card.type, "source_pages": list(card.source_pages)} for card in cards]


@app.post("/api/generate-examples")
@app.post("/api/generate-samples")
@login_required
def generate_examples():
    try:
        data, pdf_data, mode = _document_payload()
        cards = document_engine.generate_examples(pdf_data, data.get("filename", "lecture.pdf"), mode)
        return jsonify(cards=_cards_json(cards), model=document_engine.client.model)
    except (EngineError, ValueError) as exc:
        return jsonify(error=str(exc)), getattr(exc, "status_code", 400)


@app.post("/api/generate-final")
@app.post("/api/generate-deck")
@login_required
def generate_final():
    try:
        data, pdf_data, mode = _document_payload()
        feedback = {"per_card": data.get("feedback", []), "overall": data.get("generalFeedback", "")}
        cards = document_engine.generate_final_deck(pdf_data, feedback, filename=data.get("filename", "lecture.pdf"), mode=mode, target_count=int(data.get("cardCount", 50)))
        return jsonify(cards=_cards_json(cards), model=document_engine.client.model)
    except (EngineError, ValueError) as exc:
        return jsonify(error=str(exc)), getattr(exc, "status_code", 400)


@app.post("/api/export-anki")
@app.post("/api/export")
@login_required
def export_anki():
    try:
        data = request.get_json(silent=True) or {}
        cards = document_engine.export(document_engine_cards(data.get("cards", [])), str(data.get("deckName", "Document deck"))[:100])
        response = app.response_class(cards, mimetype="application/vnd.anki")
        response.headers["Content-Disposition"] = 'attachment; filename="document-deck.apkg"'
        return response
    except (EngineError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


def document_engine_cards(raw):
    try:
        from document_engine.engine import validate_cards
    except ModuleNotFoundError:
        from .document_engine.engine import validate_cards
    return validate_cards({"cards": raw})


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
