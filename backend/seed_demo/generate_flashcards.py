"""Write demo flashcard decks for Alice's current semester (HS26) into this directory's seed files.

Gives the subject page's flashcard statistics something to show: decks at different stages,
some cards mature, some learned, some unseen, a few due. Deterministic: the same rows every run.

    python backend/seed_demo/generate_flashcards.py

Adds its decks to 09_materials.json, keeping the rows it did not write (the seeded PDFs), and
writes 10_flashcards.json and 11_flashcard_progress.json (the numbers keep the load order:
decks before their cards, cards before their progress). Run it again after changing DECKS
below; generate_plan.py does not touch these files.

  Theoretical Computer Science   8 lecture decks: more than the five the page lists at first
  Systems Programming            3 decks and an Exercises folder holding two more
  Numerical Methods              2 decks, barely started
  Analysis II                    none, for the empty state
"""
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALICE = 1
# Due dates are relative to this moment, so the demo has cards due "now" around it.
REFERENCE = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
NAMESPACE = uuid.UUID("6f1c2a0e-3b7d-4e55-9a51-5d7c1b0f2e11")

# subject -> list of (deck name, card count, how far along 0..1) or (folder name, [decks]).
DECKS = {
    "course-9": [
        ("L01 Finite automata cards", 14, 0.95), ("L02 Regular languages cards", 12, 0.9),
        ("L03 Context-free grammars cards", 16, 0.8), ("L04 Pushdown automata cards", 10, 0.7),
        ("L05 Turing machines cards", 18, 0.55), ("L06 Decidability cards", 12, 0.4),
        ("L07 Reductions cards", 15, 0.2), ("L08 Complexity classes cards", 20, 0.0),
    ],
    "course-10": [
        ("01 C basics cards", 15, 0.9), ("02 Pointers and memory cards", 18, 0.6),
        ("03 Caches cards", 12, 0.3),
        ("Exercises", [("Sheet 1 cards", 8, 0.85), ("Sheet 2 cards", 9, 0.4)]),
    ],
    "course-11": [("Floating point cards", 10, 0.15), ("Linear systems cards", 14, 0.05)],
}


def ident(*parts):
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def iso(moment):
    return moment.isoformat()


def progress(rng, deck_id, card_id, stage):
    """One card's scheduler state: mature, learned (seen, not mature) or still new."""
    row = {"user_id": ALICE, "deck_id": deck_id, "card_id": card_id, "maturity": 0, "n_times_seen": 0,
           "n_mistakes": 0, "lapses": 0, "ease": 2.5, "status": "new", "learning_step": 0,
           "due": iso(REFERENCE), "last_review": None, "successful_streak": 0, "again_count": 0,
           "hard_count": 0, "good_count": 0, "easy_count": 0, "total_response_seconds": 0,
           "timed_reviews": 0, "version": 0}
    roll = rng.random()
    if roll > stage:
        return row                                          # not seen yet
    mature = roll < stage * 0.45
    interval = rng.uniform(21, 45) if mature else rng.uniform(1, 12)
    seen = rng.randint(4, 9) if mature else rng.randint(1, 4)
    mistakes = min(seen - 1, rng.choice((0, 0, 0, 1, 1, 2)))
    last = REFERENCE - timedelta(days=rng.uniform(0, interval * 1.3), hours=rng.uniform(0, 10))
    good = seen - mistakes
    easy = rng.randint(0, good // 2)
    seconds = sum(rng.uniform(4, 25) for _ in range(seen))
    row.update(maturity=round(interval, 2), n_times_seen=seen, n_mistakes=mistakes, lapses=min(mistakes, 1),
               ease=round(rng.uniform(2.2, 2.8), 2), status="review", due=iso(last + timedelta(days=interval)),
               last_review=iso(last), successful_streak=good if not mistakes else rng.randint(1, good),
               again_count=mistakes, good_count=good - easy, easy_count=easy,
               total_response_seconds=round(seconds, 1), timed_reviews=seen)
    return row


def main():
    rng = random.Random(13)
    materials, cards, states = [], [], []
    added = int(REFERENCE.timestamp() * 1000) - 30 * 86400 * 1000

    def deck(subject, parent, name, count, stage):
        nonlocal added
        deck_id = ident(subject, parent or "", name)
        added += 3_600_000
        materials.append({"id": deck_id, "user_id": ALICE, "subject_id": subject, "parent_id": parent,
                          "kind": "deck", "name": name, "category": "Slides", "marker": "To read",
                          "added_at": added})
        topic = name.removesuffix(" cards").split(" ", 1)[-1]
        for i in range(count):
            card_id = ident(deck_id, str(i))
            cards.append({"id": card_id, "deck_id": deck_id, "question": f"{topic}: question {i + 1}?",
                          "answer": f"The key point {i + 1} about {topic.lower()}.", "position": i,
                          "demo": 1, "generated": 0})
            states.append(progress(rng, deck_id, card_id, stage))

    for subject, entries in DECKS.items():
        for name, *rest in entries:
            if isinstance(rest[0], list):
                folder_id = ident(subject, "folder", name)
                added += 3_600_000
                materials.append({"id": folder_id, "user_id": ALICE, "subject_id": subject, "parent_id": None,
                                  "kind": "folder", "name": name, "category": "Exercises", "marker": "To read",
                                  "added_at": added})
                for child in rest[0]:
                    deck(subject, folder_id, *child)
            else:
                deck(subject, None, name, *rest)

    # Keep other materials (e.g. seeded PDFs), drop this script's rows from an earlier run.
    mine = {m["id"] for m in materials}
    with open(HERE / "09_materials.json") as f:
        others = [m for m in json.load(f) if m["id"] not in mine]
    materials = others + materials

    for name, rows in (("09_materials.json", materials), ("10_flashcards.json", cards),
                       ("11_flashcard_progress.json", states)):
        with open(HERE / name, "w") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"{len(materials)} materials, {len(cards)} cards")


if __name__ == "__main__":
    main()
