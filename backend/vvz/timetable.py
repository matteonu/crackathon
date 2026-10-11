"""Current course times from ETH, supplementing missing/stale times in the dump."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import logging
import re
import threading
import time
import urllib.request
from urllib.parse import parse_qs, urlparse

import db
from vvz.sync import COURSE_TYPE_NAMES, USER_AGENT

_workers = ThreadPoolExecutor(max_workers=4)
_inflight = {}
_lock = threading.Lock()


@dataclass
class Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def text(self):
        return " ".join(" ".join(c.text() if isinstance(c, Element) else c for c in self.children).split())

    def find(self, tag):
        for child in self.children:
            if isinstance(child, Element):
                if child.tag == tag:
                    yield child
                yield from child.find(tag)


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def cells(row):
    return [c for c in row.children if isinstance(c, Element) and c.tag == "td"]


def parse_timetable(html, code):
    page = Page(html).root
    if not any(h.text().startswith(code) for h in page.find("h1")) or not any(h.text() == "Courses" for h in page.find("h3")):
        raise ValueError("ETH did not return the requested course page")
    slots = []
    for row in page.find("tr"):
        columns = cells(row)
        if len(columns) < 4 or not re.fullmatch(re.escape(code[:-1]) + r"\s+[A-Z]", columns[0].text()):
            continue
        number = columns[0].text()
        previous_day = ""
        for nested in columns[3].find("tr"):
            parts = cells(nested)
            if len(parts) < 2:
                continue
            day = parts[0].text() or previous_day  # Parallel exercise rooms omit the repeated day.
            previous_day = day
            timing = re.search(r"((?:[01]\d|2[0-3]):[0-5]\d)\s*[-–]\s*((?:[01]\d|2[0-3]):[0-5]\d)", parts[1].text())
            if not timing or timing[1] >= timing[2]:
                raise ValueError("Unrecognized ETH course time")
            weekday = next((i for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")) if day.startswith(name)), None)
            date = re.match(r"^\d{1,2}\.\d{1,2}\.(?:\d{4})?", day)
            if weekday is None and date is None:
                raise ValueError("Unrecognized ETH course day")
            room = {}
            for link in nested.find("a"):
                if link.attrs.get("rel") == "map":
                    params = parse_qs(urlparse(link.attrs.get("href", "")).query)
                    room = {field: params.get(key, [None])[0] for field, key in
                            (("building", "gebaeudeMap"), ("floor", "geschossMap"), ("room", "raumMap"))}
            detail = (nested.text() + " " + " ".join(n.attrs.get("title", "") for n in nested.find("abbr"))
                      + " " + " ".join(n.attrs.get("title", "") for n in nested.find("span"))).lower()
            qualifiers = day.lower().replace(" ", "").split("/")[1:]
            slots.append(dict(lecture_number=number, weekday=weekday, date=date.group() if date else None,
                              start_time=timing[1], end_time=timing[2], building=None, floor=None, room=None,
                              first_half_semester='1' in qualifiers or bool(re.search(r"(?:1st|first) half", detail)),
                              second_half_semester='2' in qualifiers or bool(re.search(r"(?:2nd|second) half", detail)),
                              biweekly='2w' in qualifiers or any(s in detail for s in ("biweekly", "every other week", "fortnight", "14-day")),
                              inherited_from=None, type_name=COURSE_TYPE_NAMES.get(number[-1], "Class")))
            slots[-1].update(room)
    return slots


def fetch_timetable(offering):
    url = ("https://www.vvz.ethz.ch/Vorlesungsverzeichnis/lerneinheit.view"
           f"?semkez={offering['semkez']}&ansicht=ALLE&lerneinheitId={offering['id']}&lang=en")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=8) as response:
        html = response.read(2_000_001)
    if len(html) > 2_000_000:
        raise ValueError("ETH course page is too large")
    return parse_timetable(html.decode("utf-8"), offering["code"])


def refresh_timetables(sid, semkez):
    """Refresh only this user's selected courses, at most daily; retry outages after 5 min.

    Network calls never hold a database transaction. A failed refresh preserves cached
    times, and an authoritative empty timetable supersedes last year's inherited slots.
    """
    conn = db.get_db()
    now = time.time()
    offerings = [dict(r) for r in conn.execute("""
        SELECT o.*, c.code FROM semester_courses sc
        JOIN course_offerings o ON o.course_id = sc.course_id AND o.semkez = ?
        JOIN courses c ON c.id = o.course_id
        LEFT JOIN course_timetable_cache cache ON cache.course_id = o.course_id AND cache.semkez = o.semkez
        WHERE sc.semester_id = ? AND (cache.offering_id IS NULL OR cache.offering_id <> o.id OR cache.retry_after <= ?)
    """, (semkez, sid, now))]
    if not offerings:
        return

    def fetch(offering):
        try:
            return json.dumps(fetch_timetable(offering))
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).warning("Timetable lookup failed for %s/%s: %s", semkez, offering["code"], exc)
            return None

    # Several quick course additions can refresh the same semester concurrently.
    # Share those lookups instead of requesting the same ETH page repeatedly.
    pending = []
    with _lock:
        for offering in offerings:
            key = (semkez, offering['id'])
            future = _inflight.get(key)
            if future is None:
                future = _inflight[key] = _workers.submit(fetch, offering)
            pending.append((key, future))
    try:
        results = [future.result() for _, future in pending]
        with conn:
            for offering, slots in zip(offerings, results):
                conn.execute("""INSERT INTO course_timetable_cache
                (course_id, semkez, offering_id, slots, checked_at, retry_after) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(course_id, semkez) DO UPDATE SET offering_id = excluded.offering_id,
                    slots = CASE WHEN excluded.slots IS NOT NULL THEN excluded.slots
                        WHEN course_timetable_cache.offering_id = excluded.offering_id THEN course_timetable_cache.slots END,
                    checked_at = excluded.checked_at, retry_after = excluded.retry_after
                WHERE excluded.checked_at >= course_timetable_cache.checked_at""",
                    (offering["course_id"], semkez, offering["id"], slots, now, now + (86400 if slots is not None else 300)))
    finally:
        with _lock:
            for key, future in pending:
                if _inflight.get(key) is future:
                    del _inflight[key]
