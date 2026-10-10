"""Read helpers for the course catalogue in the app database (see schema.sql, `courses` and
`course_offerings`). Every function takes the database path, so tests and the CLI can point
them anywhere; the routes pass the app's DATABASE_PATH.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3

from .sync import DATABASE_PATH

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
JSON_COLUMNS = ("levels", "departments", "exam_block")


def connect(db_path: str = DATABASE_PATH):
    """A read connection that is closed when the `with` block ends."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return contextlib.closing(conn)


def _course_dict(row) -> dict:
    d = dict(row)
    for col in JSON_COLUMNS:
        if col in d:
            d[col] = json.loads(d[col] or "[]")
    return d


def status(db_path: str = DATABASE_PATH) -> dict:
    """What the sync last imported; empty before the first import."""
    with connect(db_path) as conn:
        try:
            return dict(conn.execute("SELECT key, value FROM vvz_meta").fetchall())
        except sqlite3.OperationalError:
            return {}


def semesters(db_path: str = DATABASE_PATH) -> list[str]:
    with connect(db_path) as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT semkez FROM course_offerings ORDER BY semkez")]


def search_courses(q: str = "", semkez: str | None = None, section: str | None = None, limit: int = 50,
                   db_path: str = DATABASE_PATH) -> list[dict]:
    """Courses whose code or title contains q.

    With `semkez`, only courses offered that semester, and `offering_id` is that offering.
    Without it, every course (seeded or synced), and `offering_id` is the latest offering.
    `section` matches the English programme path of the offering, e.g.
    "Computer Science Bachelor > First Year Examinations".
    """
    where, params = ["1=1"], []
    if q:
        where.append("(c.code LIKE ? OR c.title LIKE ? OR c.title_english LIKE ?)")
        params += [f"%{q}%"] * 3
    if semkez:
        offering = "SELECT o.id FROM course_offerings o WHERE o.course_id = c.id AND o.semkez = ?"
        params_offering = [semkez.upper()]
    else:
        offering = "SELECT o.id FROM course_offerings o WHERE o.course_id = c.id ORDER BY o.semkez DESC LIMIT 1"
        params_offering = []
    if section:
        where.append(f"""EXISTS (SELECT 1 FROM course_sections s WHERE s.offering_id = ({offering}) AND s.path_en LIKE ?)""")
        params += params_offering + [f"%{section}%"]
    if semkez:
        where.append(f"EXISTS ({offering})")
        params += params_offering
    sql = f"""SELECT c.id, c.code, c.title, c.title_english, c.term, c.ects, c.professor, c.weekly_hours,
                     c.language, c.exam_mode, c.exam_type, c.exam_block, c.levels, c.latest_semkez,
                     ({offering}) AS offering_id
              FROM courses c WHERE {' AND '.join(where)}
              ORDER BY c.code LIMIT ?"""
    params = params_offering + params + [int(limit)]
    with connect(db_path) as conn:
        return [_course_dict(r) for r in conn.execute(sql, params)]


def get_course(course_id: int, semkez: str | None = None, db_path: str = DATABASE_PATH) -> dict | None:
    """One course with its offering for `semkez` (default: the latest), including lectures,
    timeslots, lecturers, programme sections, plus the rating and the list of all semesters."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if row is None:
            return None
        course = _course_dict(row)
        course["offered_in"] = [r[0] for r in conn.execute(
            "SELECT semkez FROM course_offerings WHERE course_id = ? ORDER BY semkez", (course_id,))]
        rating = conn.execute("SELECT * FROM course_ratings WHERE code = ?", (course["code"],)).fetchone()
        course["rating"] = dict(rating) if rating else None
        course["resources"] = [dict(r) for r in conn.execute(
            "SELECT kind, title, url FROM course_resources WHERE course_id = ? ORDER BY id", (course_id,))]

        if semkez:
            offering = conn.execute(
                "SELECT * FROM course_offerings WHERE course_id = ? AND semkez = ?", (course_id, semkez.upper())).fetchone()
        else:
            offering = conn.execute(
                "SELECT * FROM course_offerings WHERE course_id = ? ORDER BY semkez DESC LIMIT 1", (course_id,)).fetchone()
        course["offering"] = _offering_dict(conn, offering) if offering else None
        return course


def _offering_dict(conn, offering) -> dict:
    o = dict(offering)
    o["lectures"] = [dict(r) for r in conn.execute(
        "SELECT number, title, type, type_name, hours, hour_type, comment FROM course_lectures WHERE offering_id = ? ORDER BY number",
        (o["id"],),
    )]
    for lecture in o["lectures"]:
        lecture["timeslots"] = []
    by_number = {lecture["number"]: lecture for lecture in o["lectures"]}
    for s in conn.execute(
        """SELECT lecture_number, weekday, date, start_time, end_time, building, floor, room,
                  first_half_semester, second_half_semester, biweekly, inherited_from
           FROM course_timeslots WHERE offering_id = ? ORDER BY weekday, start_time, building, room""",
        (o["id"],),
    ):
        slot = dict(s)
        number = slot.pop("lecture_number")
        slot["weekday_name"] = WEEKDAYS[slot["weekday"]] if slot["weekday"] is not None and 0 <= slot["weekday"] < 7 else None
        by_number.setdefault(number, {"number": number, "timeslots": []})["timeslots"].append(slot)
    o["lecturers"] = [dict(r) for r in conn.execute(
        """SELECT l.id, l.title, l.name, l.surname, l.department, cl.role
           FROM course_lecturers cl JOIN lecturers l ON l.id = cl.lecturer_id
           WHERE cl.offering_id = ? ORDER BY cl.role, l.surname""",
        (o["id"],),
    )]
    o["sections"] = [dict(r) for r in conn.execute(
        "SELECT section_id, type, path_en, path_de FROM course_sections WHERE offering_id = ? ORDER BY path_en",
        (o["id"],),
    )]
    return o


def weekly_timetable(course_ids: list[int], semkez: str, db_path: str = DATABASE_PATH) -> list[dict]:
    """All weekly slots of the given courses in one semester, for a timetable or clash detection."""
    if not course_ids:
        return []
    marks = ",".join("?" for _ in course_ids)
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            f"""SELECT c.id AS course_id, c.code, c.title, o.id AS offering_id, l.type, l.type_name,
                       t.weekday, t.start_time, t.end_time, t.building, t.floor, t.room,
                       t.first_half_semester, t.second_half_semester, t.biweekly, t.inherited_from
                FROM course_timeslots t
                JOIN course_offerings o ON o.id = t.offering_id
                JOIN courses c ON c.id = o.course_id
                LEFT JOIN course_lectures l ON l.offering_id = t.offering_id AND l.number = t.lecture_number
                WHERE o.course_id IN ({marks}) AND o.semkez = ? AND t.date IS NULL AND t.start_time IS NOT NULL
                ORDER BY t.weekday, t.start_time""",
            [*course_ids, semkez.upper()],
        )]
