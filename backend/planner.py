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

    PUT    /api/semesters/<semkez>/preferences         study habits and days off
    POST   /api/semesters/<semkez>/plan/generate       build a schedule proposal from them

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
from schedule_planner.main import generate_schedule
from vvz.sync import semester_of, term_of

bp = Blueprint("planner", __name__, url_prefix="/api")

SEMKEZ = re.compile(r"\d{4}[SW]")
LABEL = re.compile(r"(HS|FS)(\d{2})")
SUBJECT_ID = re.compile(r"course-(\d+)")
COLOR = re.compile(r"#[0-9a-fA-F]{6}")
START = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
MAX_RESULTS = 50
MAX_SESSIONS = 10000
MAX_DAYS_OFF = 200
# Used when neither the user nor the scraped course ratings say how hard a course is.
DEFAULT_DIFFICULTY = 3
# A full-time study week. Without it the scheduler fills every free slot before the exams,
# which over a 56-day winter phase is around 500 hours and no use to anyone. A semester whose
# study_hours_per_week is NULL is planned with this; the form shows it and can change it.
DEFAULT_HOURS_PER_WEEK = 35
# The habits of a semester that has no row yet, mirroring the defaults in schema.sql.
DEFAULT_PREFERENCES = {"dayStart": "08:00", "dayEnd": "20:00", "lunch": ["12:00", "13:00"],
                       "dinner": ["18:00", "19:00"], "studyBlockSize": 90,
                       "studyHoursPerWeek": DEFAULT_HOURS_PER_WEEK, "alpha": .3, "beta": 5,
                       "daysOff": []}
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
                    sc.desired_grade, sc.priority, sc.max_study_hours,
                    -- What the scheduler will use: the user's value, else the scraped rating, else the middle.
                    coalesce(sc.difficulty, cast(round(r.difficulty) AS INTEGER), ?) AS difficulty,
                    coalesce(sc.lecture_per_week, o.weekly_hours, c.weekly_hours) AS lecture_per_week
             FROM semester_courses sc JOIN courses c ON c.id = sc.course_id
             LEFT JOIN course_offerings o ON o.course_id = c.id AND o.semkez = ?
             LEFT JOIN course_ratings r ON r.code = c.code
             WHERE sc.semester_id = ?"""
    params = [DEFAULT_DIFFICULTY, semkez, sid]
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
            "priority": r["priority"], "difficulty": min(5, max(1, r["difficulty"])),
            "maxStudyHours": r["max_study_hours"], "lecturePerWeek": r["lecture_per_week"],
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
                   subjects=[] if sid is None else subjects(sid, semkez), sessions=sessions,
                   preferences=DEFAULT_PREFERENCES if sid is None else preferences(sid),
                   plan=None if sid is None else stored_plan(sid))


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
    if "priority" in body:
        if not isinstance(body["priority"], int) or isinstance(body["priority"], bool) or not 1 <= body["priority"] <= 5:
            raise RequestError(400, "Priority goes from 1 (most important) to 5.")
        fields["priority"] = body["priority"]
    if "difficulty" in body:
        value = body["difficulty"]
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5):
            raise RequestError(400, "Difficulty goes from 1 (easy) to 5, or leave it empty.")
        fields["difficulty"] = value
    if "maxStudyHours" in body:
        value = body["maxStudyHours"]
        if value is not None and (not number(value) or not 0 <= value <= 5000):
            raise RequestError(400, "Enter a cap from 0 to 5000 hours, or leave it empty.")
        fields["max_study_hours"] = None if value is None else round(value, 2)
    if "lecturePerWeek" in body:
        value = body["lecturePerWeek"]
        if value is not None and (not number(value) or not 0 <= value <= 60):
            raise RequestError(400, "Enter the weekly contact hours from 0 to 60, or leave it empty.")
        fields["lecture_per_week"] = None if value is None else round(value, 2)
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


# ------------------------------------------------------- study habits and the generated plan

def minutes_of(time_str):
    """'14:15' -> 855."""
    return 60 * int(time_str[:2]) + int(time_str[3:])


def semester_row(sid):
    return db.get_db().execute("SELECT * FROM semesters WHERE id = ?", (sid,)).fetchone()


def hours_per_week(row):
    """The week's study budget. A semester that has never said gets the full-time default."""
    return DEFAULT_HOURS_PER_WEEK if row["study_hours_per_week"] is None else row["study_hours_per_week"]


def preferences(sid):
    """How this semester's days are laid out, in the API's spelling."""
    row = semester_row(sid)
    return {"dayStart": row["day_start"], "dayEnd": row["day_end"],
            "lunch": [row["lunch_start"], row["lunch_end"]],
            "dinner": [row["dinner_start"], row["dinner_end"]],
            "studyBlockSize": row["study_block_size"],
            "studyHoursPerWeek": hours_per_week(row),
            "alpha": row["alpha"], "beta": row["beta"],
            "daysOff": [{"startDate": r["start_date"], "rangeLength": r["range_length"]}
                        for r in db.get_db().execute(
                            """SELECT start_date, range_length FROM semester_days_off
                               WHERE semester_id = ? ORDER BY start_date""", (sid,))]}


def scheduler_request(sid, semkez, from_date):
    """The schedule_planner request for one semester, and the course id behind each subject.

    Subjects are keyed by course code: unique, stable, and short enough to read in a dump.
    A finished course is left out, a missing difficulty falls back to the scraped course
    rating, and blocks already planned before `from_date` go in as history so the hours they
    used still count against a course's cap.
    """
    conn = db.get_db()
    row = semester_row(sid)
    end = phase(semkez)[1]
    courses = conn.execute(
        """SELECT c.id, c.code, coalesce(o.ects, c.ects, 0) AS ects,
                  coalesce(sc.lecture_per_week, o.weekly_hours, c.weekly_hours, 0) AS lectures,
                  coalesce(sc.difficulty, cast(round(r.difficulty) AS INTEGER), ?) AS difficulty,
                  sc.priority, sc.max_study_hours, coalesce(sc.exam_date, ?) AS exam_date
           FROM semester_courses sc JOIN courses c ON c.id = sc.course_id
           LEFT JOIN course_offerings o ON o.course_id = c.id AND o.semkez = ?
           LEFT JOIN course_ratings r ON r.code = c.code
           WHERE sc.semester_id = ? AND sc.completed = 0
           ORDER BY c.code""", (DEFAULT_DIFFICULTY, end, semkez, sid)).fetchall()
    if not courses:
        raise RequestError(400, "Add a course you have not finished yet, then generate a plan.")
    ids = {r["code"]: r["id"] for r in courses}
    subjects_input = {r["code"]: {
        "ects": r["ects"], "lecture_per_week": r["lectures"],
        "difficulty": min(5, max(1, r["difficulty"])), "priority": r["priority"],
        "max_study_hours": r["max_study_hours"], "examdate": r["exam_date"]} for r in courses}
    if all(subject["examdate"] <= from_date for subject in subjects_input.values()):
        raise RequestError(400, "Every exam is on or before this date. Set a later exam date first.")

    codes = {course_id: code for code, course_id in ids.items()}
    history = [{"subject": codes[r["course_id"]], "type": r["type"], "date": r["date"],
                "hours": (minutes_of(r["end_time"]) - minutes_of(r["start_time"])) / 60}
               for r in conn.execute(
                   """SELECT course_id, date, start_time, end_time, type FROM plan_blocks
                      WHERE semester_id = ? AND date < ? AND type <> 'meal' ORDER BY date, start_time""",
                   (sid, from_date))
               if r["course_id"] in codes]
    length = (dt.date.fromisoformat(end) - dt.date.fromisoformat(from_date)).days + 1
    return {
        "subjects": subjects_input,
        "history": history,
        "exam_session": {"start_date": from_date, "range_length": length},
        "days_off": [{"start_date": day["startDate"], "range_length": day["rangeLength"]}
                     for day in preferences(sid)["daysOff"]],
        "day_start": row["day_start"], "day_end": row["day_end"],
        "lunch_time": [row["lunch_start"], row["lunch_end"]],
        "dinner_time": [row["dinner_start"], row["dinner_end"]],
        "study_block_size": row["study_block_size"],
        "study_hours_per_week": hours_per_week(row),
        "alpha": row["alpha"], "beta": row["beta"],
    }, ids


def plan_payload(from_date, generated_at, plan, ids):
    """A generated plan in the shape the app reads, whether or not it was stored."""
    scheduled = plan["summary"]["scheduled_hours_per_subject"]
    active = plan["summary"]["active_learning_hours_per_subject"]
    blocks = [{"id": None, "subjectId": None if block["subject"] is None else f"course-{ids[block['subject']]}",
               "courseId": None if block["subject"] is None else ids[block["subject"]],
               "date": day["date"], "start": block["start_time"], "end": block["end_time"],
               "type": block["type"], "label": block["label"]}
              for week in plan["weeks"] for day in week["days"] for block in day["blocks"]]
    return {"generatedAt": generated_at, "fromDate": from_date, "blocks": blocks,
            "summary": [{"subjectId": f"course-{ids[code]}", "courseId": ids[code],
                         "scheduledHours": round(hours, 2),
                         "activeLearningHours": round(active.get(code, 0.0), 2)}
                        for code, hours in scheduled.items()]}


def store_plan(sid, from_date, payload, result):
    """Replace this semester's plan from `from_date` on. Earlier blocks stay as history.

    A course's target hours become what the plan asks of it, so the hours overview and the
    progress bars have something to measure recorded hours against.
    """
    conn = db.get_db()
    rows = [(sid, block["courseId"], block["date"], block["start"], block["end"],
             block["type"], block["label"]) for block in result["blocks"]]
    with conn:
        conn.execute("DELETE FROM plan_blocks WHERE semester_id = ? AND date >= ?", (sid, from_date))
        conn.executemany("""INSERT INTO plan_blocks (semester_id, course_id, date, start_time, end_time, type, label)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""", rows)
        conn.execute("""INSERT INTO study_plans (semester_id, generated_at, from_date, input_json, summary_json)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT (semester_id) DO UPDATE SET
                            generated_at = excluded.generated_at, from_date = excluded.from_date,
                            input_json = excluded.input_json, summary_json = excluded.summary_json""",
                     (sid, result["generatedAt"], from_date, json.dumps(payload),
                      json.dumps(result["summary"])))
        # Over every block held, not just this run's: earlier weeks are part of the target too.
        hours = {}
        for r in conn.execute("""SELECT course_id, start_time, end_time FROM plan_blocks
                                 WHERE semester_id = ? AND type <> 'meal' AND course_id IS NOT NULL""", (sid,)):
            hours[r["course_id"]] = hours.get(r["course_id"], 0.0) + (
                minutes_of(r["end_time"]) - minutes_of(r["start_time"])) / 60
        conn.executemany("UPDATE semester_courses SET target_hours = ? WHERE semester_id = ? AND course_id = ?",
                         [(round(total, 2), sid, course_id) for course_id, total in hours.items()])


def stored_plan(sid):
    """The plan held for a semester, or None if none was generated.

    The totals are added up from the blocks rather than taken from the last run, because the
    blocks of earlier weeks outlive the run that made them.
    """
    conn = db.get_db()
    row = conn.execute("SELECT generated_at, from_date FROM study_plans WHERE semester_id = ?",
                       (sid,)).fetchone()
    if row is None:
        return None
    blocks = [{"id": r["id"],
               "subjectId": None if r["course_id"] is None else f"course-{r['course_id']}",
               "courseId": r["course_id"], "date": r["date"], "start": r["start_time"],
               "end": r["end_time"], "type": r["type"], "label": r["label"]}
              for r in conn.execute(
                  """SELECT id, course_id, date, start_time, end_time, type, label
                     FROM plan_blocks WHERE semester_id = ?
                     ORDER BY date, start_time, end_time, type""", (sid,))]
    totals = {}
    for block in blocks:
        if block["courseId"] is None:
            continue
        entry = totals.setdefault(block["courseId"], {"subjectId": block["subjectId"],
                                                      "courseId": block["courseId"],
                                                      "scheduledHours": 0.0, "activeLearningHours": 0.0})
        hours = (minutes_of(block["end"]) - minutes_of(block["start"])) / 60
        entry["scheduledHours"] += hours
        if block["type"] == "active_learning":
            entry["activeLearningHours"] += hours
    for entry in totals.values():
        entry["scheduledHours"] = round(entry["scheduledHours"], 2)
        entry["activeLearningHours"] = round(entry["activeLearningHours"], 2)
    return {"generatedAt": row["generated_at"], "fromDate": row["from_date"], "blocks": blocks,
            "summary": [totals[course_id] for course_id in sorted(totals)]}


@bp.put("/semesters/<semkez>/preferences")
def save_preferences(semkez):
    """Study habits, and the days the user does not study. Every field is optional."""
    semkez = checked(semkez)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise RequestError(400, "Send the preferences as a JSON object.")
    sid = semester_id(current_user()["id"], semkez, create=True)
    row = semester_row(sid)
    fields = {}

    for key, column in (("dayStart", "day_start"), ("dayEnd", "day_end")):
        if key in body:
            if not isinstance(body[key], str) or not START.fullmatch(body[key]):
                raise RequestError(400, f"{key} must be a time of day like 08:00.")
            fields[column] = body[key]
    for key, columns in (("lunch", ("lunch_start", "lunch_end")),
                         ("dinner", ("dinner_start", "dinner_end"))):
        if key in body:
            value = body[key]
            if (not isinstance(value, list) or len(value) != 2
                    or not all(isinstance(t, str) and START.fullmatch(t) for t in value)
                    or value[0] >= value[1]):
                raise RequestError(400, f"{key} must be a start and an end time, like [\"12:00\", \"13:00\"].")
            fields[columns[0]], fields[columns[1]] = value
    if fields.get("day_start", row["day_start"]) >= fields.get("day_end", row["day_end"]):
        raise RequestError(400, "The day has to end after it starts.")
    if "studyBlockSize" in body:
        size = body["studyBlockSize"]
        if not isinstance(size, int) or isinstance(size, bool) or not 15 <= size <= 240:
            raise RequestError(400, "Choose a study block of 15 to 240 minutes.")
        fields["study_block_size"] = size
    if "studyHoursPerWeek" in body:
        value = body["studyHoursPerWeek"]
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)
                                  or not 0 <= value <= 7 * 24):
            raise RequestError(400, "Enter whole hours a week from 0 to 168, or leave it empty for no limit.")
        fields["study_hours_per_week"] = value
    for key, column, low, high in (("alpha", "alpha", 0, 5), ("beta", "beta", 1e-6, 100)):
        if key in body:
            if not number(body[key]) or not low <= body[key] <= high:
                raise RequestError(400, f"{key} must be a number between {low} and {high}.")
            fields[column] = float(body[key])

    days_off = None
    if "daysOff" in body:
        value = body["daysOff"]
        if not isinstance(value, list) or len(value) > MAX_DAYS_OFF:
            raise RequestError(400, f"Send up to {MAX_DAYS_OFF} days off as a list.")
        days_off, seen = [], set()
        for item in value:
            if not isinstance(item, dict) or not iso_date(item.get("startDate")):
                raise RequestError(400, "Every day off needs a startDate like 2026-12-24.")
            length = item.get("rangeLength", 1)
            if not isinstance(length, int) or isinstance(length, bool) or not 1 <= length <= 400:
                raise RequestError(400, "A day off can span 1 to 400 days.")
            if item["startDate"] in seen:
                raise RequestError(400, f"{item['startDate']} is listed twice.")
            seen.add(item["startDate"])
            days_off.append((sid, item["startDate"], length))

    if not fields and days_off is None:
        raise RequestError(400, "Nothing to change.")
    conn = db.get_db()
    with conn:
        if fields:
            conn.execute(f"UPDATE semesters SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                         [*fields.values(), sid])
        if days_off is not None:
            conn.execute("DELETE FROM semester_days_off WHERE semester_id = ?", (sid,))
            conn.executemany("INSERT INTO semester_days_off (semester_id, start_date, range_length) VALUES (?, ?, ?)",
                             days_off)
    return jsonify(preferences(sid))


@bp.post("/semesters/<semkez>/plan/generate")
def generate_plan(semkez):
    """Build a schedule proposal for the rest of the study phase.

    `fromDate` is the first day to plan, defaulting to today clamped into the study phase, so
    pressing the button again next week keeps the weeks already behind. `dryRun` returns the
    proposal without storing it, which is what the preview dialog asks for.
    """
    semkez = checked(semkez)
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise RequestError(400, "Send the options as a JSON object.")
    sid = semester_id(current_user()["id"], semkez)
    if sid is None:
        raise RequestError(400, f"Add a course to your {label_of(semkez)} first.")
    start, end = phase(semkez)
    from_date = body.get("fromDate")
    if from_date is None:
        from_date = min(max(dt.date.today().isoformat(), start), end)
    elif not iso_date(from_date) or not start <= from_date <= end:
        raise RequestError(400, f"fromDate must be a date in the study phase, {start} to {end}.")

    payload, ids = scheduler_request(sid, semkez, from_date)
    try:
        result = generate_schedule(payload)
    except ValueError as exc:
        # Every rejection from the scheduler is already a sentence a user can act on.
        raise RequestError(400, str(exc)) from None
    plan = plan_payload(from_date, dt.datetime.now().astimezone().isoformat(timespec="seconds"), result, ids)
    if not body.get("dryRun"):
        store_plan(sid, from_date, payload, plan)
        plan = stored_plan(sid)
    return jsonify(plan)
