"""Read-only calendar occurrences from the caller's saved VVZ course times."""
import datetime as dt
import re

import db


def easter(year):
    """Gregorian Easter Sunday, used for ETH's lecture-free week after Easter."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    return dt.date(year, n // 31, n % 31 + 1)


def teaching_period(semkez):
    # ETH's published teaching weeks (not the separate, existing Lernphase):
    # https://ethz.ch/staffnet/en/news-and-events/academic-calendar.html
    year = int(semkez[:4])
    first, last = (38, 51) if semkez.endswith("W") else (8, 22)
    return dt.date.fromisocalendar(year, first, 1), dt.date.fromisocalendar(year, last, 7)


def timetable(sid, semkez, study_start):
    start, end = teaching_period(semkez)
    end = min(end, dt.date.fromisoformat(study_start) - dt.timedelta(days=1))
    result = {"start": start.isoformat(), "end": end.isoformat(), "events": []}
    if sid is None:
        return result
    rows = db.get_db().execute("""
        SELECT t.*, o.course_id, l.type_name
        FROM semester_courses sc
        JOIN course_offerings o ON o.course_id = sc.course_id AND o.semkez = ?
        JOIN course_timeslots t ON t.offering_id = o.id
        LEFT JOIN course_lectures l ON l.offering_id = t.offering_id AND l.number = t.lecture_number
        WHERE sc.semester_id = ? ORDER BY t.id
    """, (semkez, sid)).fetchall()
    spring = semkez.endswith("S")
    easter_monday = easter(start.year) + dt.timedelta(days=1)
    dates = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    teaching_weeks = sorted({day - dt.timedelta(days=day.weekday()) for day in dates
                             if not (spring and easter_monday <= day < easter_monday + dt.timedelta(days=7))})
    grouped = {}
    for row in rows:
        begin, finish = row["start_time"], row["end_time"]
        if not all(isinstance(t, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in (begin, finish)) or begin >= finish:
            continue
        once = None
        if row["date"]:
            # A dated event copied from last year's catalogue is not a current appointment.
            if row["inherited_from"]:
                continue
            try:
                raw = row["date"].strip().rstrip(".")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                    once = dt.date.fromisoformat(raw)
                else:
                    parts = [int(part) for part in raw.split(".")]
                    once = dt.date(parts[2] if len(parts) == 3 else start.year, parts[1], parts[0])
            except (ValueError, IndexError):
                continue
        for day in dates:
            if once is not None:
                if day != once:
                    continue
            else:
                monday = day - dt.timedelta(days=day.weekday())
                if day.weekday() != row["weekday"] or monday not in teaching_weeks:
                    continue
                week = teaching_weeks.index(monday)
                first, second = row["first_half_semester"], row["second_half_semester"]
                if first != second and ((first and week >= 7) or (second and week < 7)):
                    continue
                if row["biweekly"] and week % 2:
                    continue
            key = (row["course_id"], row["lecture_number"], day.isoformat(), begin, finish)
            room = " ".join(str(row[field]) for field in ("building", "floor", "room") if row[field])
            if key not in grouped:
                grouped[key] = {"id": f"course-{row['id']}-{day.isoformat()}", "subjectId": f"course-{row['course_id']}",
                                "date": day.isoformat(), "start": begin, "end": finish,
                                "label": (row["type_name"] or "Class").capitalize(), "rooms": [],
                                "inheritedFrom": row["inherited_from"], "biweekly": bool(row["biweekly"])}
            if room and room not in grouped[key]["rooms"]:
                grouped[key]["rooms"].append(room)
    result["events"] = sorted(grouped.values(), key=lambda event: (event["date"], event["start"], event["id"]))
    return result
