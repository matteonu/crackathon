"""Read helpers for the local VVZ database built by `python -m vvz.sync`.

All functions open a short-lived read-only connection, so they stay correct while
the sync swaps in a freshly built file underneath.
"""

from __future__ import annotations

import json
import os
import sqlite3

from .sync import DB_PATH

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class NotSynced(RuntimeError):
    """Raised when vvz.db does not exist yet."""


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise NotSynced(f"{db_path} does not exist; run `python -m vvz.sync` first")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _unit_dict(row) -> dict:
    d = dict(row)
    for col in ("levels", "departments", "exam_block"):
        d[col] = json.loads(d.get(col) or "[]")
    return d


def status(db_path: str = DB_PATH) -> dict:
    with connect(db_path) as conn:
        return dict(conn.execute("SELECT key, value FROM vvz_meta").fetchall())


def semesters(db_path: str = DB_PATH) -> list[str]:
    with connect(db_path) as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT semkez FROM vvz_units ORDER BY semkez")]


def search_units(q: str = "", semkez: str | None = None, section: str | None = None, limit: int = 50, db_path: str = DB_PATH) -> list[dict]:
    """Units whose number or title contains q, optionally in one semester and programme section.

    `section` matches the English section path, e.g. "Computer Science Bachelor > 1. Semester".
    """
    where, params = ["1=1"], []
    if q:
        where.append("(u.number LIKE ? OR u.title LIKE ? OR u.title_english LIKE ?)")
        params += [f"%{q}%"] * 3
    if semkez:
        where.append("u.semkez = ?")
        params.append(semkez.upper())
    if section:
        where.append("EXISTS (SELECT 1 FROM vvz_unit_sections s WHERE s.unit_id = u.id AND s.path_en LIKE ?)")
        params.append(f"%{section}%")
    sql = f"""SELECT u.id, u.semkez, u.number, u.title, u.title_english, u.credits, u.weekly_hours,
                     u.language, u.exam_mode, u.exam_type, u.exam_block, u.levels, u.departments
              FROM vvz_units u WHERE {' AND '.join(where)}
              ORDER BY u.semkez DESC, u.number LIMIT ?"""
    params.append(int(limit))
    with connect(db_path) as conn:
        return [_unit_dict(r) for r in conn.execute(sql, params)]


def get_unit(unit_id: int, db_path: str = DB_PATH) -> dict | None:
    """One unit with its courses, timeslots, lecturers, programme sections and rating."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM vvz_units WHERE id = ?", (unit_id,)).fetchone()
        if row is None:
            return None
        unit = _unit_dict(row)
        unit["courses"] = [dict(r) for r in conn.execute(
            "SELECT number, title, type, type_name, hours, hour_type, comment FROM vvz_courses WHERE unit_id = ? ORDER BY number",
            (unit_id,),
        )]
        for course in unit["courses"]:
            course["timeslots"] = []
        for s in [dict(r) for r in conn.execute(
            """SELECT course_number, weekday, date, start_time, end_time, building, floor, room,
                      first_half_semester, second_half_semester, biweekly, inherited_from
               FROM vvz_timeslots WHERE unit_id = ? ORDER BY weekday, start_time, building, room""",
            (unit_id,),
        )]:
            number = s.pop("course_number")
            s["weekday_name"] = WEEKDAYS[s["weekday"]] if s["weekday"] is not None and 0 <= s["weekday"] < 7 else None
            for course in unit["courses"]:
                if course["number"] == number:
                    course["timeslots"].append(s)
        unit["lecturers"] = [dict(r) for r in conn.execute(
            """SELECT l.id, l.title, l.name, l.surname, l.department, ul.role
               FROM vvz_unit_lecturers ul JOIN vvz_lecturers l ON l.id = ul.lecturer_id
               WHERE ul.unit_id = ? ORDER BY ul.role, l.surname""",
            (unit_id,),
        )]
        unit["sections"] = [dict(r) for r in conn.execute(
            "SELECT section_id, type, path_en, path_de FROM vvz_unit_sections WHERE unit_id = ? ORDER BY path_en",
            (unit_id,),
        )]
        rating = conn.execute("SELECT * FROM vvz_ratings WHERE number = ?", (unit["number"],)).fetchone()
        unit["rating"] = dict(rating) if rating else None
        return unit


def weekly_timetable(unit_ids: list[int], db_path: str = DB_PATH) -> list[dict]:
    """All weekly slots of the given units, for building a timetable or finding clashes."""
    if not unit_ids:
        return []
    marks = ",".join("?" for _ in unit_ids)
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            f"""SELECT t.unit_id, u.number AS unit_number, u.title, c.type, c.type_name,
                       t.weekday, t.start_time, t.end_time, t.building, t.floor, t.room,
                       t.first_half_semester, t.second_half_semester, t.biweekly, t.inherited_from
                FROM vvz_timeslots t
                JOIN vvz_units u ON u.id = t.unit_id
                JOIN vvz_courses c ON c.unit_id = t.unit_id AND c.number = t.course_number AND c.semkez = t.semkez
                WHERE t.unit_id IN ({marks}) AND t.date IS NULL AND t.start_time IS NOT NULL
                ORDER BY t.weekday, t.start_time""",
            unit_ids,
        )]
