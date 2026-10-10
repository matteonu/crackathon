"""Deck content and stable-card reconciliation. All writes use the caller's transaction."""
from datetime import datetime, timezone
import json
import uuid

from errors import RequestError


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def card_source(card, source_pdf=None):
    if not card["source_pdf_name"] or not card["source_pages"]:
        return None
    return {"pdfId": card["source_pdf_id"], "pdfName": source_pdf["name"] if source_pdf else card["source_pdf_name"],
            "pages": json.loads(card["source_pages"]), "evidence": card["source_evidence"] or ""}


def deck_cards(conn, deck_id):
    sources = {r["id"]: r for r in conn.execute("""SELECT id, name FROM materials WHERE id IN
        (SELECT source_pdf_id FROM flashcards WHERE deck_id=?)""", (deck_id,))}
    return [{"id": r["id"], "question": r["question"], "answer": r["answer"],
             "demo": bool(r["demo"]), "generated": bool(r["generated"]),
             **({"source": source} if (source := card_source(r, sources.get(r["source_pdf_id"]))) else {})}
            for r in conn.execute("SELECT * FROM flashcards WHERE deck_id = ? ORDER BY position, id", (deck_id,))]


def ensure_deck(conn, source, mode=None):
    found = conn.execute("SELECT * FROM materials WHERE kind = 'deck' AND source_pdf_id = ?",
                         (source["id"],)).fetchone()
    if found:
        return found["id"]
    deck_id = str(uuid.uuid4())
    base = source["name"].rsplit(".", 1)[0][:140] + " cards"
    name, suffix = base, 2
    while conn.execute("""SELECT 1 FROM materials WHERE user_id = ? AND subject_id = ?
                           AND parent_id IS ? AND lower(name) = lower(?)""",
                       (source["user_id"], source["subject_id"], source["parent_id"], name)).fetchone():
        name = f"{base} ({suffix})"
        suffix += 1
    conn.execute("""INSERT INTO materials
        (id, user_id, subject_id, parent_id, kind, name, category, marker, added_at, source_pdf_id, generation_mode)
        VALUES (?, ?, ?, ?, 'deck', ?, ?, 'To read', ?, ?, ?)""",
        (deck_id, source["user_id"], source["subject_id"], source["parent_id"], name,
         source["category"], source["added_at"] + 1, source["id"], mode))
    return deck_id


def validate_cards(cards):
    if not isinstance(cards, list) or len(cards) > 10000:
        raise RequestError(400, "Provide a list of at most 10000 cards.")
    for card in cards:
        if (not isinstance(card, dict) or not isinstance(card.get("question"), str)
                or not card["question"].strip() or len(card["question"]) > 4000
                or not isinstance(card.get("answer"), str) or not card["answer"].strip()
                or len(card["answer"]) > 8000):
            raise RequestError(400, "Each card needs a question and an answer within the supported length.")
        if "id" in card and (not isinstance(card["id"], str) or not card["id"] or len(card["id"]) > 200):
            raise RequestError(400, "Invalid card ID.")
        source = card.get("source")
        if source is not None:
            if (not isinstance(source, dict) or set(source) != {"pdfId", "pdfName", "pages", "evidence"}
                    or (source["pdfId"] is not None and (not isinstance(source["pdfId"], str) or not source["pdfId"]))
                    or not isinstance(source["pdfName"], str) or not source["pdfName"].strip() or len(source["pdfName"]) > 180
                    or not isinstance(source["pages"], list) or not 1 <= len(source["pages"]) <= 100
                    or any(type(page) is not int or page < 1 for page in source["pages"])
                    or not isinstance(source["evidence"], str) or not source["evidence"].strip() or len(source["evidence"]) > 8000):
                raise RequestError(400, "A card source needs a PDF, positive page numbers and supporting evidence.")
    ids = [c["id"] for c in cards if "id" in c]
    if len(ids) != len(set(ids)):
        raise RequestError(400, "Card IDs must be unique within a deck.")


def reset_progress(conn, deck_id, card_id):
    # Increment rather than recreate: an old open tab must not rate changed content.
    conn.execute("""UPDATE flashcard_progress SET maturity=0, n_times_seen=0, n_mistakes=0,
        lapses=0, ease=2.5, status='new', learning_step=0, due=?, last_review=NULL,
        successful_streak=0, again_count=0, hard_count=0, good_count=0, easy_count=0,
        total_response_seconds=0, timed_reviews=0, version=version+1 WHERE deck_id=? AND card_id=?""",
        (utc_now(), deck_id, card_id))


def replace_cards(conn, deck_id, cards):
    validate_cards(cards)
    deck = conn.execute("SELECT * FROM materials WHERE id=? AND kind='deck'", (deck_id,)).fetchone()
    if not deck:
        raise RequestError(404, "This deck does not exist.")
    existing = {c["id"]: c for c in deck_cards(conn, deck_id)}
    seen = set()
    for position, card in enumerate(cards):
        card_id = card.get("id") or str(uuid.uuid4())
        other = conn.execute("SELECT deck_id FROM flashcards WHERE id=?", (card_id,)).fetchone()
        if other and other["deck_id"] != deck_id:
            raise RequestError(400, "This card ID belongs to another deck.")
        previous = existing.get(card_id)
        changed = previous and (previous["question"], previous["answer"]) != (card["question"], card["answer"])
        if changed:
            reset_progress(conn, deck_id, card_id)
        source = card.get("source", previous.get("source") if previous and not changed else None)
        if source and source["pdfId"]:
            pdf = conn.execute("SELECT id,name FROM materials WHERE id=? AND user_id=? AND kind='pdf'",
                               (source["pdfId"], deck["user_id"])).fetchone()
            if not pdf:
                raise RequestError(400, "Choose a source PDF from your library.")
            source = {**source, "pdfName": pdf["name"]}
        conn.execute("""INSERT INTO flashcards(id,deck_id,question,answer,position,demo,generated,
            source_pdf_id,source_pdf_name,source_pages,source_evidence)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET question=excluded.question,
            answer=excluded.answer,position=excluded.position,demo=excluded.demo,generated=excluded.generated,
            source_pdf_id=excluded.source_pdf_id,source_pdf_name=excluded.source_pdf_name,
            source_pages=excluded.source_pages,source_evidence=excluded.source_evidence""",
            (card_id, deck_id, card["question"], card["answer"], position,
             bool(card.get("demo", False)), bool(card.get("generated", False)),
             source["pdfId"] if source else None, source["pdfName"] if source else None,
             json.dumps(sorted(set(source["pages"]))) if source else None, source["evidence"] if source else None))
        conn.execute("""INSERT OR IGNORE INTO flashcard_progress(user_id,deck_id,card_id,due)
            VALUES(?,?,?,?)""", (deck["user_id"], deck_id, card_id, utc_now()))
        seen.add(card_id)
    for card_id in existing.keys() - seen:
        # Startup rebuilds materials with foreign keys disabled inside its transaction.
        # Perform this cascade explicitly too, so removed cards cannot orphan progress.
        conn.execute("DELETE FROM flashcard_progress WHERE card_id=? AND deck_id=?", (card_id, deck_id))
        conn.execute("DELETE FROM flashcards WHERE id=? AND deck_id=?", (card_id, deck_id))


def sync_generated(conn, source, questions, mode):
    deck_id = ensure_deck(conn, source, mode)
    old = deck_cards(conn, deck_id)
    manual = [c for c in old if not c["generated"] and not c["demo"]]
    # Exact content matches retain identity even if generation reorders the cards.
    available = [c for c in old if c["generated"] or c["demo"]]
    generated = []
    for card in questions:
        match = next((c for c in available if (c["question"], c["answer"]) ==
                      (card["question"], card["answer"])), None)
        if match:
            available.remove(match)
        reference = ({"pdfId": source["id"], "pdfName": source["name"], "pages": card["source_pages"],
                      "evidence": card["evidence"]} if card.get("source_pages") and card.get("evidence")
                     else card.get("source", match.get("source") if match else None))
        generated.append({**card, **({"source": reference} if reference else {}), "id": match["id"] if match else str(uuid.uuid4()),
                          "generated": True, "demo": False})
    replace_cards(conn, deck_id, generated + manual)
    conn.execute("UPDATE materials SET generation_mode=? WHERE id=?", (mode, deck_id))
    return deck_id


def migrate_embedded_cards(conn):
    """Idempotently extract old card JSON; keep summaries on their source materials."""
    for source in conn.execute("SELECT * FROM materials WHERE kind!='deck' AND outputs IS NOT NULL").fetchall():
        outputs = json.loads(source["outputs"])
        if not isinstance(outputs, dict) or "flashcards" not in outputs:
            continue
        cards = outputs["flashcards"].get("cards", [])
        if cards:
            validate_cards(cards)
            mode = (json.loads(source["processing"] or "{}")).get("mode", "shallow")
            deck_id = ensure_deck(conn, source, mode if source["kind"] == "pdf" else None)
            if source["kind"] != "pdf":
                conn.execute("UPDATE materials SET source_pdf_id=NULL WHERE id=?", (deck_id,))
            # An older app can write embedded cards after this PDF already has a deck.
            # Reuse its identities and progress; consume matches once for duplicate Q/A.
            available = deck_cards(conn, deck_id)
            migrated = []
            for card in cards:
                match = next((c for c in available if c["id"] == card.get("id")), None)
                if match is None:
                    match = next((c for c in available if (c["question"], c["answer"]) ==
                                  (card["question"], card["answer"])), None)
                if match:
                    available.remove(match)
                # Unknown legacy IDs may belong to other decks; allocate fresh ones.
                migrated.append({**(match or {}), **card,
                                 "id": match["id"] if match else str(uuid.uuid4())})
            migrated.extend(c for c in available if not c["generated"] and not c["demo"])
            replace_cards(conn, deck_id, migrated)
        del outputs["flashcards"]
        conn.execute("UPDATE materials SET outputs=? WHERE id=?", (json.dumps(outputs), source["id"]))


def persist_result(conn, source_id, result):
    if result.get("status") != "complete":
        return
    document = result["documents"][0]
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        source = conn.execute("SELECT * FROM materials WHERE id=? AND kind='pdf'", (source_id,)).fetchone()
        if not source:
            return
        task = result.get("task", "flashcards")
        if task == "flashcards":
            sync_generated(conn, source, document["questions"], result.get("mode", "shallow"))
        outputs = json.loads(source["outputs"] or "{}")
        outputs.pop("flashcards", None)
        outputs["summary"] = {"text": document["abstract"]}
        previous = json.loads(source["processing"] or "{}")
        processing = {"status": "complete", "mode": result.get("mode", "shallow"), "task": task,
                      "requestedQuestions": (previous.get("requestedQuestions") or 60) if task == "summary"
                      else result.get("requested_questions", 60), "error": ""}
        conn.execute("UPDATE materials SET outputs=?,processing=? WHERE id=?",
                     (json.dumps(outputs), json.dumps(processing), source_id))
