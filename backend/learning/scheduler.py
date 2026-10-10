"""Scheduling rules extracted from anki_flashcard_scheduler.ipynb; no app state or I/O."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
import json
import math


def _utc(value=None):
    value = datetime.now(timezone.utc) if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Use a timezone-aware datetime.")
    return value.astimezone(timezone.utc)


@dataclass
class Flashcard:
    question: str
    answer: str
    maturity: float = 0.0  # Current review interval in days.
    n_times_seen: int = 0
    n_mistakes: int = 0
    lapses: int = 0  # Failures after graduation to review.
    ease: float = 2.5
    status: str = "new"
    learning_step: int = 0
    due: datetime | None = None
    last_review: datetime | None = None
    successful_streak: int = 0
    rating_counts: dict = field(default_factory=lambda: dict.fromkeys(
        ("again", "hard", "good", "easy"), 0))
    total_response_seconds: float = 0.0
    timed_reviews: int = 0

    @property
    def is_mature(self):
        return self.status == "review" and self.maturity >= 21



class FlashcardScheduler:
    """An Anki-like interval scheduler with recursive stratified sampling.

    Collection nodes are folder dictionaries, card lists, or question/answer
    dictionaries. Indices are tuples of folder names and list positions.
    Folder priorities are positive weights (larger means more reviews).
    This uses an SM-2-style ease/interval model, rather than Anki's FSRS model.
    """

    RATINGS = {1: "again", 2: "hard", 3: "good", 4: "easy"}

    def __init__(self, collection, folder_priorities=None, *, now=None):
        self.cards = {}
        self.folders = {()}
        self.folder_priorities = {}
        self.review_log = []
        created = _utc(now)

        def visit(node, path):
            if isinstance(node, dict) and set(node) == {"question", "answer"}:
                if not all(isinstance(value, str) for value in node.values()):
                    raise ValueError("Card questions and answers must be strings.")
                self.cards[path] = Flashcard(**node, due=created)
            elif isinstance(node, dict):
                self.folders.add(path)
                for name, child in node.items():
                    if not isinstance(name, str) or not name:
                        raise ValueError("Folder names must be non-empty strings.")
                    visit(child, path + (name,))
            elif isinstance(node, list):
                self.folders.add(path)
                for index, child in enumerate(node):
                    if not isinstance(child, dict) or set(child) != {"question", "answer"}:
                        raise ValueError("Lists must contain question/answer dictionaries.")
                    visit(child, path + (index,))
            else:
                raise ValueError("Use nested folder dictionaries and lists of cards.")

        visit(collection, ())
        for path, priority in (folder_priorities or {}).items():
            self.set_folder_priority(path, priority)

    @staticmethod
    def _path(path):
        # Tuple paths also support folder names containing '/'.
        if isinstance(path, str):
            return tuple(path.split("/")) if path else ()
        if isinstance(path, (tuple, list)):
            return tuple(path)
        raise ValueError("Paths must be tuples, lists, or slash-separated strings.")

    def set_folder_priority(self, path, priority):
        path = self._path(path)
        if path not in self.folders:
            raise ValueError(f"Unknown folder: {path}")
        if (isinstance(priority, bool) or not isinstance(priority, (int, float))
                or not math.isfinite(priority) or priority <= 0):
            raise ValueError("Folder priorities must be finite positive numbers.")
        self.folder_priorities[path] = float(priority)

    def get_card(self, index):
        return self.cards[self._path(index)]

    def get_session(self, limit=20, *, now=None, new_card_limit=None):
        """Return ordered indices of due cards without changing their progress.

        A card appears at most once. Call again after rating cards to include
        failed cards once their short relearning delay has elapsed. The new-card
        limit applies to this call, not to the entire day.
        """
        now = _utc(now)
        for name, value in (("limit", limit), ("new_card_limit", new_card_limit)):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer.")
        if limit is None:
            raise ValueError("limit must be a non-negative integer.")

        def urgency(index):
            card = self.cards[index]
            # Due learning/relearning first, due reviews second, unseen last.
            phase = 2 if card.status == "new" else (0 if card.status in
                    ("learning", "relearning") else 1)
            overdue = max(0, (now - card.due).total_seconds() / 86400)
            error_rate = card.n_mistakes / max(1, card.n_times_seen)
            return (phase, -overdue / max(card.maturity, 1 / 1440),
                    -error_rate, card.maturity)

        eligible = [index for index, card in self.cards.items() if card.due <= now]
        eligible.sort(key=urgency)

        def stratify(indices, prefix):
            leaves = [index for index in indices if len(index) == len(prefix)
                      or isinstance(index[len(prefix)], int)]
            groups = {}
            for index in indices:
                if index in leaves:
                    continue
                child = prefix + (index[len(prefix)],)
                groups.setdefault(child, []).append(index)
            queues = {child: stratify(items, child) for child, items in groups.items()}
            if leaves:
                queues[prefix] = leaves
            served = Counter()
            positions = Counter()
            result = []
            while queues:
                # Weighted fair interleaving at EVERY level. Existing cards'
                # urgency breaks ties; folder weight determines review frequency.
                child = min(queues, key=lambda key: (
                    served[key] / self.folder_priorities.get(key, 1.0),
                    urgency(queues[key][positions[key]]),
                    -self.folder_priorities.get(key, 1.0)))
                result.append(queues[child][positions[child]])
                positions[child] += 1
                served[child] += 1
                if positions[child] == len(queues[child]):
                    del queues[child]
            return result

        session = []
        new_count = 0
        for index in stratify(eligible, ()):
            if len(session) >= limit:
                break
            if self.cards[index].status == "new":
                if new_card_limit is not None and new_count >= new_card_limit:
                    continue
                new_count += 1
            session.append(index)
        return session

    def review(self, index, rating, *, now=None, response_seconds=None):
        """Apply a rating and return the card's next due datetime.

        Learning steps: 1 and 10 minutes; graduation: 1 day, easy: 4 days.
        Mature reviews grow by ease; a lapse reduces the interval and triggers
        a 10-minute relearning step. Recall failures count as mistakes everywhere.
        """
        index = self._path(index)
        card = self.cards[index]
        now = _utc(now)
        if isinstance(rating, bool):
            raise ValueError("Rating must be again/hard/good/easy or integer 1–4.")
        if type(rating) is int:
            rating = self.RATINGS.get(rating)
        if rating not in ("again", "hard", "good", "easy"):
            raise ValueError("Rating must be again/hard/good/easy or integer 1–4.")
        if card.last_review is not None and now < card.last_review:
            raise ValueError("Review time cannot precede the previous review.")
        if response_seconds is not None and (
                isinstance(response_seconds, bool)
                or not isinstance(response_seconds, (int, float))
                or not math.isfinite(response_seconds) or response_seconds < 0):
            raise ValueError("response_seconds must be finite and non-negative.")

        previous_status = card.status
        card.n_times_seen += 1
        card.rating_counts[rating] += 1
        card.last_review = now
        if response_seconds is not None:
            card.total_response_seconds += response_seconds
            card.timed_reviews += 1
        if rating == "again":
            card.n_mistakes += 1
            card.successful_streak = 0
        else:
            card.successful_streak += 1

        if previous_status == "review":
            if rating == "again":
                card.lapses += 1
                card.ease = max(1.3, card.ease - .2)
                card.maturity = max(1.0, card.maturity * .5)
                card.status = "relearning"
                delay = timedelta(minutes=10)
            else:
                factor = {"hard": 1.2, "good": card.ease, "easy": card.ease * 1.3}[rating]
                card.maturity = min(36500.0, max(1.0, card.maturity * factor))
                card.ease = max(1.3, card.ease + {"hard": -.15, "good": 0, "easy": .15}[rating])
                delay = timedelta(days=card.maturity)
        elif previous_status == "relearning":
            if rating in ("again", "hard"):
                delay = timedelta(minutes=10 if rating == "again" else 15)
            else:
                card.status = "review"
                if rating == "easy":
                    card.maturity = max(4.0, card.maturity * 1.3)
                delay = timedelta(days=card.maturity)
        elif rating == "easy":
            card.status = "review"
            card.maturity = 4.0
            delay = timedelta(days=4)
        elif rating == "good" and previous_status == "learning" and card.learning_step == 1:
            card.status = "review"
            card.maturity = 1.0
            delay = timedelta(days=1)
        else:
            card.status = "learning"
            if rating == "again":
                card.learning_step = 0
                delay = timedelta(minutes=1)
            elif rating == "good":
                card.learning_step = 1
                delay = timedelta(minutes=10)
            else:
                delay = timedelta(minutes=5.5 if card.learning_step == 0 else 15)
        card.due = now + delay
        self.review_log.append({"index": list(index), "rating": rating,
                                "reviewed_at": now.isoformat(),
                                "response_seconds": response_seconds})
        return card.due

    def analytics(self, *, now=None):
        """Return totals for root and each folder, including all descendants."""
        now = _utc(now)
        result = []
        for path in sorted(self.folders, key=lambda path: (len(path), path)):
            cards = [card for index, card in self.cards.items() if index[:len(path)] == path]
            reviews = sum(card.n_times_seen for card in cards)
            mistakes = sum(card.n_mistakes for card in cards)
            timed = sum(card.timed_reviews for card in cards)
            states = Counter(card.status for card in cards)
            result.append({
                "path": list(path), "priority": self.folder_priorities.get(path, 1.0),
                "cards": len(cards), "reviews": reviews, "mistakes": mistakes,
                "lapses": sum(card.lapses for card in cards),
                "success_rate": (reviews - mistakes) / reviews if reviews else None,
                "due_cards": sum(card.due <= now for card in cards),
                "overdue_review_cards": sum(card.status == "review" and card.due < now for card in cards),
                "states": {state: states[state] for state in ("new", "learning", "review", "relearning")},
                "mature_cards": sum(card.is_mature for card in cards),
                "average_interval_days": sum(card.maturity for card in cards) / len(cards) if cards else 0,
                "average_response_seconds": sum(card.total_response_seconds for card in cards) / timed if timed else None,
                "ratings": {rating: sum(card.rating_counts[rating] for card in cards)
                            for rating in self.RATINGS.values()},
            })
        return result

    def to_state(self):
        """JSON-compatible snapshot; save alongside the unchanged collection."""
        cards = []
        for index, card in self.cards.items():
            data = asdict(card)
            for key in ("due", "last_review"):
                data[key] = data[key].isoformat() if data[key] else None
            cards.append({"index": list(index), **data})
        return {"version": 1, "cards": cards,
                "folder_priorities": [{"path": list(path), "priority": value}
                                      for path, value in self.folder_priorities.items()],
                "review_log": [dict(event, index=list(event["index"])) for event in self.review_log]}

    @classmethod
    def from_state(cls, collection, state):
        """Restore a trusted snapshot, rejecting moved/changed cards."""
        if state.get("version") != 1:
            raise ValueError("Unsupported state version.")
        scheduler = cls(collection)
        indices = [tuple(item["index"]) for item in state["cards"]]
        if len(indices) != len(set(indices)) or set(indices) != set(scheduler.cards):
            raise ValueError("State does not match the collection's card indices.")
        for item in state["cards"]:
            data = dict(item)
            index = tuple(data.pop("index"))
            original = scheduler.cards[index]
            if (data["question"], data["answer"]) != (original.question, original.answer):
                raise ValueError(f"Card content changed at {index}; use a fresh state.")
            for key in ("due", "last_review"):
                data[key] = _utc(datetime.fromisoformat(data[key])) if data[key] else None
            scheduler.cards[index] = Flashcard(**data)
        for item in state["folder_priorities"]:
            scheduler.set_folder_priority(item["path"], item["priority"])
        scheduler.review_log = [dict(event, index=list(event["index"])) for event in state["review_log"]]
        return scheduler

