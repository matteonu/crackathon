"""The caller's study plan on top of the VVZ catalogue: which courses they take in a semester.

    GET    /api/semesters                              current, selected, available and the caller's semesters
    PUT    /api/semesters/selected          {semkez}   the semester the caller is looking at
    GET    /api/semesters/<semkez>/courses             the caller's courses in that semester
    POST   /api/semesters/<semkez>/courses  {courseId} add one (creates the semester row on first use)
    DELETE /api/semesters/<semkez>/courses/<courseId>  remove one
    GET    /api/courses?q=&semkez=&limit=              search the courses offered in a semester

    GET    /api/semesters/<semkez>/plan                the whole study plan of that semester
    PATCH  /api/semesters/<semkez>/courses/<courseId>  target hours, exam date, done, next action, colour
    PUT    /api/semesters/<semkez>/courses/<courseId>/hours/<date>  {hours} recorded on a day (null clears)
    PUT    /api/semesters/<semkez>/sessions            [{id, subjectId, date, start, hours}] replaces them all

In the app each course is a subject with id 'course-<courseId>'. A semester's study phase -- the
days hours can be recorded and sessions planned for -- is its Lernphase before the exams.

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
SUBJECT_ID = re.compile(r"course-(\d+)")
COLOR = re.compile(r"#[0-9a-fA-F]{6}")
START = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
MAX_RESULTS = 50
MAX_SESSIONS = 10000
# Colours of new subjects, in order of adding; the same family as the frontend's.
COLORS = ("#2598A2", "#E4AC17", "#D56568", "#5586CA", "#DD792F", "#6E9A5A", "#9A6BB8", "#C2577E")

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


def phase(semkez):
    """The study phase before a semester's exams, as ISO dates: HS 21 Dec - 14 Feb, FS 1 Jun - 31 Aug."""
    year = int(semkez[:4])
    if semkez.endswith("W"):
        return f"{year}-12-21", f"{year + 1}-02-14"
    return f"{year}-06-01", f"{year}-08-31"


def iso_date(value):
    try:
        return isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def available():
    return [r[0] for r in db.get_db().execute(
        "SELECT DISTINCT semkez FROM course_offerings ORDER BY semkez")]


def own_semesters(user_id):
    """The semesters the user has a plan for, as VVZ keys."""
    labels = (r[0] for r in db.get_db().execute("SELECT label FROM semesters WHERE user_id = ?", (user_id,)))
    return sorted(filter(None, map(semkez_of, labels)))


def checked(semkez):
    """A semester the caller can open: in the catalogue, or one they already have a plan for.
    The latter keeps old plans reachable once the VVZ sync stops importing their semester."""
    semkez = (semkez or "").upper()
    if not SEMKEZ.fullmatch(semkez) or (semkez not in available() and semkez not in own_semesters(current_user()["id"])):
        raise RequestError(400, "This semester is not available.")
    return semkez


def in_catalogue(semkez):
    """A semester the catalogue has offerings for: only there can courses be searched and added."""
    semkez = (semkez or "").upper()
    if not SEMKEZ.fullmatch(semkez) or semkez not in available():
        raise RequestError(400, "Courses can only be added to semesters in the course catalogue.")
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
    catalogue = available()
    user = current_user()
    today = semester_of(dt.date.today())
    current = today if today in catalogue or not catalogue else catalogue[-1]
    offered = sorted(set(catalogue) | set(own_semesters(user["id"])))
    stored = user["selected_semkez"] if "selected_semkez" in user.keys() else None
    selected = stored if stored in offered else current
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
    return jsonify(current=current, selected=selected,
                   available=[{"semkez": s, "label": label_of(s), "inCatalogue": s in catalogue} for s in offered],
                   mine=sorted(mine, key=lambda m: m["semkez"]))


@bp.put("/semesters/selected")
def select_semester():
    """Remembers which semester the caller is looking at, across devices."""
    semkez = checked((request.get_json(silent=True) or {}).get("semkez"))
    conn = db.get_db()
    with conn:
        conn.execute("UPDATE users SET selected_semkez = ? WHERE id = ?", (semkez, current_user()["id"]))
    return jsonify(selected=semkez)


@bp.get("/semesters/<semkez>/courses")
def list_courses(semkez):
    return jsonify(entries(current_user()["id"], checked(semkez)))


@bp.post("/semesters/<semkez>/courses")
def add_course(semkez):
    semkez = in_catalogue(semkez)
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
    count = conn.execute("SELECT count(*) FROM semester_courses WHERE semester_id = ?", (sid,)).fetchone()[0]
    with conn:
        added = conn.execute(
            """INSERT INTO semester_courses (semester_id, course_id, color, exam_date) VALUES (?, ?, ?, ?)
               ON CONFLICT DO NOTHING""",
            (sid, course_id, COLORS[count % len(COLORS)], phase(semkez)[1])).rowcount
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
    semkez = in_catalogue(request.args.get("semkez"))
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


# ------------------------------------------------------------------ the study plan

def subjects(sid, semkez, course_id=None):
    """The semester's courses as the app's subjects, with the hours recorded for each."""
    conn = db.get_db()
    hours = {}
    for r in conn.execute("SELECT course_id, date, hours FROM study_hours WHERE semester_id = ? ORDER BY date", (sid,)):
        hours.setdefault(r["course_id"], {})[r["date"]] = r["hours"]
    sql = """SELECT c.id, c.code, coalesce(c.title_english, o.title, c.title) AS title, coalesce(o.ects, c.ects) AS ects,
                    o.id AS offering_id, sc.target_hours, sc.exam_date, sc.completed, sc.next_action, sc.color,
                    sc.desired_grade
             FROM semester_courses sc JOIN courses c ON c.id = sc.course_id
             LEFT JOIN course_offerings o ON o.course_id = c.id AND o.semkez = ?
             WHERE sc.semester_id = ?"""
    params = [semkez, sid]
    if course_id is not None:
        sql += " AND c.id = ?"
        params.append(course_id)
    result = []
    for i, r in enumerate(conn.execute(sql + " ORDER BY sc.rowid", params)):
        result.append({
            "id": f"course-{r['id']}", "courseId": r["id"], "name": r["title"], "shortName": r["title"],
            "color": r["color"] or COLORS[i % len(COLORS)], "targetHours": r["target_hours"],
            "examDate": r["exam_date"] or phase(semkez)[1], "completed": bool(r["completed"]),
            "nextAction": r["next_action"], "ects": r["ects"], "lectureId": r["code"],
            "homepage": vvz_url(semkez, r["offering_id"]), "desiredGrade": r["desired_grade"],
            "hours": hours.get(r["id"], {}),
        })
    return result


def taken(semkez, course_id):
    """(semester id, course id) of a course in the caller's semester, or a 404."""
    sid = semester_id(current_user()["id"], semkez)
    if sid is None or not db.get_db().execute(
            "SELECT 1 FROM semester_courses WHERE semester_id = ? AND course_id = ?", (sid, course_id)).fetchone():
        raise RequestError(404, f"This course is not in your {label_of(semkez)}.")
    return sid, course_id


@bp.get("/semesters/<semkez>/plan")
def plan(semkez):
    semkez = checked(semkez)
    start, end = phase(semkez)
    sid = semester_id(current_user()["id"], semkez)
    sessions = [] if sid is None else [
        {"id": r["id"], "subjectId": f"course-{r['course_id']}", "date": r["date"], "start": r["start"], "hours": r["hours"]}
        for r in db.get_db().execute(
            "SELECT id, course_id, date, start, hours FROM study_sessions WHERE semester_id = ? ORDER BY date, start",
            (sid,))]
    return jsonify(semkez=semkez, label=label_of(semkez), start=start, end=end,
                   subjects=[] if sid is None else subjects(sid, semkez), sessions=sessions)


@bp.patch("/semesters/<semkez>/courses/<int:course_id>")
def update_course(semkez, course_id):
    semkez = checked(semkez)
    sid, course_id = taken(semkez, course_id)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise RequestError(400, "Send the fields to change as a JSON object.")
    fields = {}
    if "targetHours" in body:
        if not number(body["targetHours"]) or not 0 <= body["targetHours"] <= 5000:
            raise RequestError(400, "Enter target hours from 0 to 5000.")
        fields["target_hours"] = round(body["targetHours"], 2)
    if "examDate" in body:
        if not iso_date(body["examDate"]):
            raise RequestError(400, "Enter a valid exam date.")
        fields["exam_date"] = body["examDate"]
    if "completed" in body:
        if not isinstance(body["completed"], bool):
            raise RequestError(400, "completed must be true or false.")
        fields["completed"] = int(body["completed"])
    if "nextAction" in body:
        if not isinstance(body["nextAction"], str) or len(body["nextAction"]) > 1000:
            raise RequestError(400, "Keep the next action under 1000 characters.")
        fields["next_action"] = body["nextAction"]
    if "color" in body:
        if not isinstance(body["color"], str) or not COLOR.fullmatch(body["color"]):
            raise RequestError(400, "Choose a colour like #2598A2.")
        fields["color"] = body["color"]
    if "desiredGrade" in body:
        grade = body["desiredGrade"]
        if grade is not None and (not number(grade) or not 1 <= grade <= 6):
            raise RequestError(400, "Enter a grade from 1 to 6.")
        fields["desired_grade"] = grade
    if not fields:
        raise RequestError(400, "Nothing to change.")
    conn = db.get_db()
    with conn:
        conn.execute(f"UPDATE semester_courses SET {', '.join(f'{k} = ?' for k in fields)} "
                     "WHERE semester_id = ? AND course_id = ?", [*fields.values(), sid, course_id])
    return jsonify(subjects(sid, semkez, course_id)[0])


@bp.put("/semesters/<semkez>/courses/<int:course_id>/hours/<date>")
def record_hours(semkez, course_id, date):
    semkez = checked(semkez)
    sid, course_id = taken(semkez, course_id)
    start, end = phase(semkez)
    if not iso_date(date) or not start <= date <= end:
        raise RequestError(400, f"Choose a date in the study phase ({start} to {end}).")
    hours = (request.get_json(silent=True) or {}).get("hours")
    conn = db.get_db()
    if hours is None:
        with conn:
            conn.execute("DELETE FROM study_hours WHERE semester_id = ? AND course_id = ? AND date = ?", (sid, course_id, date))
        return jsonify(date=date, hours=None)
    if not number(hours) or not 0 <= hours <= 24:
        raise RequestError(400, "Enter a number between 0 and 24 hours.")
    hours = round(hours, 2)
    others = conn.execute("SELECT coalesce(sum(hours), 0) FROM study_hours WHERE semester_id = ? AND date = ? AND course_id != ?",
                          (sid, date, course_id)).fetchone()[0]
    if round(others + hours, 2) > 24:
        raise RequestError(400, "The combined study time for this day cannot exceed 24 hours.")
    with conn:
        conn.execute("""INSERT INTO study_hours (semester_id, course_id, date, hours) VALUES (?, ?, ?, ?)
                        ON CONFLICT (semester_id, course_id, date) DO UPDATE SET hours = excluded.hours""",
                     (sid, course_id, date, hours))
    return jsonify(date=date, hours=hours)


@bp.put("/semesters/<semkez>/sessions")
def save_sessions(semkez):
    semkez = checked(semkez)
    body = request.get_json(silent=True)
    if not isinstance(body, list) or len(body) > MAX_SESSIONS:
        raise RequestError(400, "Send the planned sessions as a list.")
    sid = semester_id(current_user()["id"], semkez)
    courses = set() if sid is None else {r[0] for r in db.get_db().execute(
        "SELECT course_id FROM semester_courses WHERE semester_id = ?", (sid,))}
    start, end = phase(semkez)
    rows, ids = [], set()
    invalid = RequestError(400, "Check the subject, date, start time, and duration. Sessions must end by midnight.")
    for item in body:
        if not isinstance(item, dict):
            raise invalid
        session_id, match = item.get("id"), SUBJECT_ID.fullmatch(str(item.get("subjectId", "")))
        date, begin, hours = item.get("date"), item.get("start"), item.get("hours")
        if (not isinstance(session_id, str) or not 0 < len(session_id) <= 64 or session_id in ids
                or not match or int(match.group(1)) not in courses
                or not iso_date(date) or not start <= date <= end
                or not isinstance(begin, str) or not START.fullmatch(begin)
                or not number(hours) or not 0 < hours <= 24
                or int(begin[:2]) * 60 + int(begin[3:]) + hours * 60 > 24 * 60):
            raise invalid
        ids.add(session_id)
        rows.append((sid, session_id, int(match.group(1)), date, begin, hours))
    # Sorted by day and start, two sessions overlap exactly when one starts before the previous ends.
    by_time = sorted(rows, key=lambda r: (r[3], r[4]))
    for prev, cur in zip(by_time, by_time[1:]):
        minutes = lambda r: int(r[4][:2]) * 60 + int(r[4][3:])
        if prev[3] == cur[3] and minutes(cur) < minutes(prev) + prev[5] * 60:
            raise RequestError(400, "Study sessions cannot overlap. Choose another time.")
    if sid is not None:
        conn = db.get_db()
        with conn:
            conn.execute("DELETE FROM study_sessions WHERE semester_id = ?", (sid,))
            conn.executemany("INSERT INTO study_sessions (semester_id, id, course_id, date, start, hours) VALUES (?, ?, ?, ?, ?, ?)", rows)
    return jsonify(saved=len(rows))
