import base64
import binascii

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_required

from .engine.engine import DocumentEngine, EngineError, validate_cards
from .engine.llm import ModelClient
from .engine.models import Card, ProcessingMode

bp = Blueprint("flashcards", __name__, url_prefix="/api/flashcards")


def get_engine() -> DocumentEngine:
    """One engine per app, configured from app.config. Tests can replace it in app.extensions."""
    if "flashcards_engine" not in current_app.extensions:
        cfg = current_app.config
        client = ModelClient(model=cfg["MODEL"], api_key=cfg["OPENAI_API_KEY"], endpoint=cfg["OPENAI_ENDPOINT"])
        current_app.extensions["flashcards_engine"] = DocumentEngine(client)
    return current_app.extensions["flashcards_engine"]


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
    return [{"front": c.front, "back": c.back, "type": c.type, "source_pages": list(c.source_pages)} for c in cards]


def _error(exc):
    return jsonify(error=str(exc)), getattr(exc, "status_code", 400)


@bp.post("/examples")
@login_required
def examples():
    try:
        data, pdf_data, mode = _document_payload()
        engine = get_engine()
        cards = engine.generate_examples(pdf_data, data.get("filename", "lecture.pdf"), mode)
        return jsonify(cards=_cards_json(cards), model=engine.client.model)
    except (EngineError, ValueError) as exc:
        return _error(exc)


@bp.post("/final")
@login_required
def final():
    try:
        data, pdf_data, mode = _document_payload()
        engine = get_engine()
        feedback = {"per_card": data.get("feedback", []), "overall": data.get("generalFeedback", "")}
        cards = engine.generate_final_deck(
            pdf_data, feedback, filename=data.get("filename", "lecture.pdf"), mode=mode,
            target_count=int(data.get("cardCount", 50)),
        )
        return jsonify(cards=_cards_json(cards), model=engine.client.model)
    except (EngineError, ValueError) as exc:
        return _error(exc)


@bp.post("/export")
@login_required
def export():
    try:
        data = request.get_json(silent=True) or {}
        cards = validate_cards({"cards": data.get("cards", [])})
        deck = get_engine().export(cards, str(data.get("deckName", "Document deck"))[:100])
        response = current_app.response_class(deck, mimetype="application/vnd.anki")
        response.headers["Content-Disposition"] = 'attachment; filename="deck.apkg"'
        return response
    except (EngineError, ValueError) as exc:
        return _error(exc)
