"""Tiny local server for Cardinal.

The browser talks only to this server. The OpenAI key never enters client-side
code or a response. The API boundary is intentionally small so it can later be
replaced by a hosted worker without changing the UI contract.
"""
import base64
import json
import os
import re
import sqlite3
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).parent
MODEL = "gpt-5-mini"
MAX_PDF_BYTES = 50 * 1024 * 1024


def api_key():
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value:
        return value
    key_path = ROOT / "assets" / "openai-key.txt"
    return key_path.read_text(encoding="utf-8").strip() if key_path.exists() else ""


def valid_api_key():
    value = api_key()
    return value.startswith("sk-") and len(value) > 20


def safe_cards(payload):
    """Deterministically validate and deduplicate model output."""
    raw = payload.get("cards", []) if isinstance(payload, dict) else []
    cleaned, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        front = re.sub(r"\s+", " ", str(item.get("front", "")).strip())
        back = re.sub(r"\s+", " ", str(item.get("back", "")).strip())
        kind = str(item.get("type", "basic")).lower().strip()
        if not front or not back or len(front) > 500 or len(back) > 2000:
            continue
        fingerprint = (front.casefold(), back.casefold())
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        cleaned.append({"front": front, "back": back, "type": kind if kind in {"basic", "cloze", "application"} else "basic", "source": str(item.get("source", "")).strip()[:120]})
    return cleaned


def call_openai(document, filename, feedback=None, sample_count=5):
    instruction = f"""You create high-quality Anki flashcards from lecture slides.
Return only JSON matching this schema: {{\"cards\":[{{\"front\":string,\"back\":string,\"type\":\"basic\"|\"cloze\"|\"application\",\"source\":string}}]}}.
Create about {sample_count} representative cards. Prefer atomic prompts, precise answers, and slide references when visible. Never invent facts. Apply the learner feedback if present."""
    if feedback:
        instruction += "\nLearner feedback: " + json.dumps(feedback, ensure_ascii=False)
    content = [{"type": "input_text", "text": instruction}]
    if document:
        content.append({"type": "input_file", "filename": filename, "file_data": "data:application/pdf;base64," + document})
    body = {"model": MODEL, "input": [{"role": "user", "content": content}], "text": {"format": {"type": "json_object"}}}
    request = Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(), method="POST", headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"})
    with urlopen(request, timeout=90) as response:
        result = json.loads(response.read().decode())
    output = result.get("output", [])
    text = "".join(part.get("text", "") for item in output if item.get("type") == "message" for part in item.get("content", []) if part.get("type") == "output_text")
    return safe_cards(json.loads(text))


def make_apkg(cards, deck_name):
    """Write a small, valid Anki package using only the Python standard library."""
    temp = ROOT / f".collection-{uuid.uuid4().hex}.anki2"
    now = int(time.time() * 1000)
    con = sqlite3.connect(temp)
    con.executescript("""CREATE TABLE col (id integer primary key, crt integer not null, mod integer not null, scm integer not null, ver integer not null, dty integer not null, usn integer not null, ls integer not null, conf text not null, models text not null, decks text not null, dconf text not null, tags text not null);
    CREATE TABLE notes (id integer primary key, guid text not null, mid integer not null, mod integer not null, usn integer not null, tags text not null, flds text not null, sfld integer not null, csum integer not null, flags integer not null, data text not null);
    CREATE TABLE cards (id integer primary key, nid integer not null, did integer not null, ord integer not null, mod integer not null, usn integer not null, type integer not null, queue integer not null, due integer not null, ivl integer not null, factor integer not null, reps integer not null, lapses integer not null, left integer not null, odue integer not null, odid integer not null, flags integer not null, data text not null);""")
    deck_id = now
    model_id = now + 1
    models = {str(model_id): {"name": "Cardinal Basic", "type": 0, "mod": now, "usn": -1, "sortf": 0, "did": deck_id, "tmpls": [{"name": "Card 1", "ord": 0, "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}], "flds": [{"name": "Front", "ord": 0}, {"name": "Back", "ord": 1}]}}
    decks = {"1": {"name": "Default", "id": 1, "mod": 0, "usn": 0, "desc": ""}, str(deck_id): {"name": deck_name, "id": deck_id, "mod": now, "usn": -1, "desc": "Generated by Cardinal"}}
    con.execute("INSERT INTO col VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (1, now // 1000, now, 11, 0, 0, -1, 0, '{}', json.dumps(models), json.dumps(decks), '{}', ''))
    for index, card in enumerate(cards):
        note_id, card_id = now + index + 10, now + index + 1000
        front, back = card["front"], card["back"]
        con.execute("INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?,?,?)", (note_id, uuid.uuid4().hex[:10], model_id, now, -1, '', front + '\x1f' + back, front, 0, 0, ''))
        con.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (card_id, note_id, deck_id, 0, now, -1, 0, 0, index + 1, 0, 0, 0, 0, 0, 0, 0, 0, ''))
    con.commit(); con.close()
    output = ROOT / f".deck-{uuid.uuid4().hex}.apkg"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(temp, "collection.anki2")
        archive.writestr("media", "{}")
    temp.unlink(missing_ok=True)
    return output.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/health":
            self.send_json(200, {"ok": True, "model": MODEL, "keyConfigured": valid_api_key()}); return
        requested = self.path.lstrip("/") or "index.html"
        path = (ROOT / requested).resolve()
        if path.is_file() and ROOT in path.parents:
            content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "text/css" if path.suffix == ".css" else "application/javascript"
            data = path.read_bytes(); self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_PDF_BYTES * 2:
            self.send_json(413, {"error": "Payload is too large."}); return
        try:
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/generate-samples":
                if not valid_api_key():
                    self.send_json(500, {"error": "OpenAI API key is missing or invalid. Replace assets/openai-key.txt with a valid API key."}); return
                cards = call_openai(payload.get("pdfBase64", ""), payload.get("filename", "lecture.pdf"), payload.get("feedback"))
                self.send_json(200, {"cards": cards, "model": MODEL}); return
            if self.path == "/api/generate-deck":
                if not valid_api_key():
                    self.send_json(500, {"error": "OpenAI API key is missing or invalid. Replace assets/openai-key.txt with a valid API key."}); return
                feedback = {"per_card": payload.get("feedback", []), "overall": payload.get("generalFeedback", "")}
                cards = call_openai(payload.get("pdfBase64", ""), payload.get("filename", "lecture.pdf"), feedback, int(payload.get("cardCount", 50)))
                self.send_json(200, {"cards": cards, "model": MODEL}); return
            if self.path == "/api/export":
                cards = safe_cards(payload); deck = make_apkg(cards, str(payload.get("deckName", "Cardinal deck"))[:100])
                self.send_response(200); self.send_header("Content-Type", "application/vnd.anki"); self.send_header("Content-Disposition", 'attachment; filename="cardinal-deck.apkg"'); self.send_header("Content-Length", str(len(deck))); self.end_headers(); self.wfile.write(deck); return
            self.send_error(404)
        except (HTTPError, URLError, json.JSONDecodeError, ValueError) as error:
            detail = getattr(error, "read", lambda: b"")()
            self.send_json(502, {"error": "The model request could not be completed.", "detail": detail.decode(errors="ignore")[:300]})
        except Exception as error:
            self.send_json(500, {"error": "The deck could not be generated.", "detail": str(error)[:300]})

    def log_message(self, *_):
        return


if __name__ == "__main__":
    print("Cardinal running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
