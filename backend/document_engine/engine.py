"""Application workflow for the current examination flow."""

from __future__ import annotations

import re

from . import anki, pdf
from .llm import ModelClient
from .models import Card, DocumentContext, ProcessingMode


class EngineError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class DocumentEngine:
    def __init__(self, client: ModelClient | None = None):
        self.client = client or ModelClient()

    def create_context(self, data: bytes, filename: str, mode: ProcessingMode = ProcessingMode.QUICK) -> DocumentContext:
        try:
            mode = ProcessingMode(mode)
            return DocumentContext(filename=filename or "lecture.pdf", pages=pdf.prepare_pages(data, mode), mode=mode)
        except (ValueError, pdf.PDFError) as exc:
            raise EngineError(str(exc)) from exc

    def generate_examples(self, data: bytes, filename: str = "lecture.pdf", mode: ProcessingMode = ProcessingMode.QUICK) -> list[Card]:
        context = self.create_context(data, filename, mode)
        try:
            result = self.client.generate_json(context, purpose="examples", target_count=5)
        except Exception as exc:
            raise EngineError(str(exc), 502) from exc
        return validate_cards(result)

    def generate_final_deck(self, data: bytes, feedback=None, *, filename: str = "lecture.pdf", mode: ProcessingMode = ProcessingMode.QUICK, target_count: int = 50) -> list[Card]:
        context = self.create_context(data, filename, mode)
        try:
            result = self.client.generate_json(context, purpose="final_cards", feedback=feedback, target_count=target_count)
        except Exception as exc:
            raise EngineError(str(exc), 502) from exc
        return validate_cards(result)

    def export(self, cards: list[Card], deck_name: str = "Document deck") -> bytes:
        return anki.export_apkg(validate_cards({"cards": [card.__dict__ for card in cards]}), deck_name)


def validate_cards(payload) -> list[Card]:
    raw = payload.get("cards", []) if isinstance(payload, dict) else []
    result, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        front = re.sub(r"\s+", " ", str(item.get("front", "")).strip())
        back = re.sub(r"\s+", " ", str(item.get("back", "")).strip())
        if not front or not back or len(front) > 500 or len(back) > 2000:
            continue
        key = (front.casefold(), back.casefold())
        if key in seen:
            continue
        seen.add(key)
        kind = str(item.get("type", "basic")).lower().strip()
        if kind not in {"basic", "cloze", "application"}:
            kind = "basic"
        source_pages = item.get("source_pages", [])
        if not isinstance(source_pages, (list, tuple)):
            source_pages = []
        pages = tuple(int(page) for page in source_pages if str(page).isdigit())
        result.append(Card(front, back, kind, pages))
    return result
