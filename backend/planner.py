"""The caller's study plan on top of the VVZ catalogue: which courses they take in a semester.

    GET    /api/semesters                              current, available and the caller's semesters
    GET    /api/semesters/<semkez>/courses             the caller's courses in that semester
    POST   /api/semesters/<semkez>/courses  {courseId} add one (creates the semester row on first use)
    DELETE /api/semesters/<semkez>/courses/<courseId>  remove one
    GET    /api/courses?q=&semkez=&limit=              search the courses offered in a semester

Semesters are VVZ keys in the API ('2026W' = autumn 2026, '2027S' = spring 2027) and the
app's labels in the database (semesters.label: 'HS26', 'FS27'). A semester is usable once
the VVZ sync has imported offerings for it. Every row is scoped to the caller.
"""
import datetime as dt
import json
import re

from flask import Blueprint, jsonify, request

from auth import current_user
import db
from errors import RequestError
from vvz.sync import semester_of, term_of

bp = Blueprint("planner", __name__, url_prefix="/api")

SEMKEZ = re.compile(r"\d{4}[SW]")
LABEL = re.compile(r"(HS|FS)(\d{2})")
MAX_RESULTS = 50

# The offering's lecturers, as 'Prof. Dr. Ada Lovelace, Dr. Alan Turing'.
LECTURERS = """(SELECT group_concat(trim(coalesce(l.title || ' ', '') || coalesce(l.name, '') || ' ' || coalesce(l.surname, '')), ', ')
                FROM course_lecturers cl JOIN lecturers l ON l.id = cl.lecturer_id
                WHERE cl.offering_id = o.id AND cl.role = 'lecturer')"""


def label_of(semkez):
    """'2026W' -> 'HS26', '2027S' -> 'FS27'."""
    return f"{term_of(semkez)}{semkez[2:4]}"


def semkez_of(label):
    """'HS26' -> '2026W'; None for a label that is not one of ours."""
    match = LABEL.fullmatch(label or "")
    if not match:
        return None
    return f"20{match.group(2)}{'W' if match.group(1) == 'HS' else 'S'}"


def vvz_url(semkez, offering_id):
    """The course's page in the ETH course catalogue; offering ids are VVZ lerneinheitIds."""
    if offering_id is None:
        return None
    return ("https://www.vvz.ethz.ch/Vorlesungsverzeichnis/lerneinheit.view"
            f"?semkez={semkez}&ansicht=ALLE&lerneinheitId={offering_id}&lang=en")


def available():
    return [r[0] for r in db.get_db().execute(
        "SELECT DISTINCT semkez FROM course_offerings ORDER BY semkez")]


def checked(semkez):
    """The semester key, if it is well-formed and the catalogue has offerings for it."""
    semkez = (semkez or "").upper()
    if not SEMKEZ.fullmatch(semkez) or semkez not in available():
        raise RequestError(400, "This semester is not in the course catalogue.")
    return semkez


def semester_id(user_id, semkez, create=False):
    conn = db.get_db()
    if create:
        with conn:
            conn.execute("INSERT INTO semesters (user_id, label) VALUES (?, ?) ON CONFLICT (user_id, label) DO NOTHING",
                         (user_id, label_of(semkez)))
    row = conn.execute("SELECT id FROM semesters WHERE user_id = ? AND label = ?",
                       (user_id, label_of(semkez))).fetchone()
    return row["id"] if row else None


def entries(user_id, semkez, course_id=None):
    """The caller's courses in one semester, with that semester's offering details."""
    sql = f"""SELECT c.id, c.code, coalesce(c.title_english, o.title, c.title) AS title,
                     coalesce(o.ects, c.ects) AS ects, coalesce({LECTURERS}, c.professor) AS professor,
                     coalesce(o.weekly_hours, c.weekly_hours) AS weeklyHours, sc.desired_grade AS desiredGrade,
                     o.id AS offeringId
              FROM semesters s
              JOIN semester_courses sc ON sc.semester_id = s.id
              JOIN courses c ON c.id = sc.course_id
              LEFT JOIN course_offerings o ON o.course_id = c.id AND o.semkez = ?
              WHERE s.user_id = ? AND s.label = ?"""
    params = [semkez, user_id, label_of(semkez)]
    if course_id is not None:
        sql += " AND c.id = ?"
        params.append(course_id)
    rows = db.get_db().execute(sql + " ORDER BY c.code", params)
    return [{**dict(r), "term": term_of(semkez), "vvzUrl": vvz_url(semkez, r["offeringId"])} for r in rows]


@bp.get("/semesters")
def semesters():
    options = available()
    today = semester_of(dt.date.today())
    current = today if today in options or not options else options[-1]
    mine = []
    for r in db.get_db().execute(
        """SELECT s.label, count(sc.course_id) AS courseCount, coalesce(sum(c.ects), 0) AS ectsTotal
           FROM semesters s
           LEFT JOIN semester_courses sc ON sc.semester_id = s.id
           LEFT JOIN courses c ON c.id = sc.course_id
           WHERE s.user_id = ? GROUP BY s.id ORDER BY s.label""",
        (current_user()["id"],),
    ):
        semkez = semkez_of(r["label"])
        if semkez:
            mine.append({"semkez": semkez, **dict(r)})
    return jsonify(current=current, available=[{"semkez": s, "label": label_of(s)} for s in options],
                   mine=sorted(mine, key=lambda m: m["semkez"]))


@bp.get("/semesters/<semkez>/courses")
def list_courses(semkez):
    return jsonify(entries(current_user()["id"], checked(semkez)))


@bp.post("/semesters/<semkez>/courses")
def add_course(semkez):
    semkez = checked(semkez)
    body = request.get_json(silent=True) or {}
    course_id = body.get("courseId")
    if not isinstance(course_id, int) or isinstance(course_id, bool):
        raise RequestError(400, "Choose a course to add.")
    conn = db.get_db()
    offered = conn.execute("SELECT 1 FROM course_offerings WHERE course_id = ? AND semkez = ?",
                           (course_id, semkez)).fetchone()
    if not offered:
        raise RequestError(400, f"This course is not offered in {label_of(semkez)}.")
    user_id = current_user()["id"]
    sid = semester_id(user_id, semkez, create=True)
    with conn:
        added = conn.execute("INSERT INTO semester_courses (semester_id, course_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                             (sid, course_id)).rowcount
    if not added:
        raise RequestError(409, f"This course is already in your {label_of(semkez)}.")
    return jsonify(entries(user_id, semkez, course_id)[0]), 201


@bp.delete("/semesters/<semkez>/courses/<int:course_id>")
def remove_course(semkez, course_id):
    semkez = checked(semkez)
    sid = semester_id(current_user()["id"], semkez)
    conn = db.get_db()
    with conn:
        removed = sid is not None and conn.execute(
            "DELETE FROM semester_courses WHERE semester_id = ? AND course_id = ?", (sid, course_id)).rowcount
    if not removed:
        raise RequestError(404, f"This course is not in your {label_of(semkez)}.")
    return jsonify(deleted=course_id)


@bp.get("/courses")
def search():
    semkez = checked(request.args.get("semkez"))
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        raise RequestError(400, "Type at least 2 characters to search.")
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), MAX_RESULTS))
    except ValueError:
        raise RequestError(400, "limit must be a whole number.") from None
    # The user's text is matched literally: % and _ are not wildcards.
    escaped = re.sub(r"([\\%_])", r"\\\1", q)
    contains, prefix = f"%{escaped}%", f"{escaped}%"
    sid = semester_id(current_user()["id"], semkez)
    rows = db.get_db().execute(
        f"""SELECT c.id, c.code, coalesce(c.title_english, o.title, c.title) AS title,
                   coalesce(o.ects, c.ects) AS ects, coalesce({LECTURERS}, c.professor) AS professor,
                   coalesce(o.weekly_hours, c.weekly_hours) AS weeklyHours, c.levels, c.language,
                   EXISTS (SELECT 1 FROM semester_courses sc WHERE sc.semester_id = :sid AND sc.course_id = c.id) AS added
            FROM courses c JOIN course_offerings o ON o.course_id = c.id AND o.semkez = :semkez
            WHERE c.code LIKE :contains ESCAPE '\\' OR c.title LIKE :contains ESCAPE '\\'
               OR c.title_english LIKE :contains ESCAPE '\\'
            ORDER BY CASE WHEN c.code LIKE :prefix ESCAPE '\\' THEN 0
                          WHEN coalesce(c.title_english, c.title) LIKE :prefix ESCAPE '\\' THEN 1 ELSE 2 END,
                     title, c.code
            LIMIT :limit""",
        {"sid": sid, "semkez": semkez, "contains": contains, "prefix": prefix, "limit": limit},
    )
    return jsonify([{**dict(r), "levels": json.loads(r["levels"] or "[]"), "added": bool(r["added"])} for r in rows])
