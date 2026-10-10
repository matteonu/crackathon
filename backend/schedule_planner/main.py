"""Turn one JSON request into a study plan.

    from schedule_planner import generate_schedule
    plan = generate_schedule({"subjects": {...}, "exam_session": {...}, ...})

`generate_schedule` is the whole public surface: plain JSON in, plain JSON out, no state and
no clock, so the HTTP layer only has to build the request from the database and store the
blocks that come back. Every rejection is a ValueError whose message can be shown to a user.

It also runs on its own, for trying parameters out by hand:

    python -m schedule_planner.main < tests/example_input.json
"""
import json
import re
import sys

from .dayrange import DayRange, iso_date
from .schedule import Schedule, WEEKS_IN_SEMESTER

TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
DEFAULTS = {"day_start": "08:00", "day_end": "20:00", "lunch_time": ("12:00", "13:00"),
            "dinner_time": ("18:00", "19:00"), "study_block_size": 90, "alpha": .3, "beta": 5}


def _time(value, field):
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise ValueError(f"{field} must be a time of day like '08:00'.")
    return value


def _interval(value, field):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field} must be a start and an end time.")
    start, end = _time(value[0], field), _time(value[1], field)
    if start >= end:
        raise ValueError(f"{field} must start before it ends.")
    return (start, end)


def _number(value, field):
    """A finite number. Rejects None, booleans, strings, NaN and the infinities."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number.")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be a finite number.")
    return float(value)


def _whole(value, field, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be a whole number of at least {minimum}.")
    return value


def _subject(name, subject):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Every subject needs a name.")
    if not isinstance(subject, dict):
        raise ValueError(f"{name}: a subject must be an object.")
    values = {field: _number(subject.get(field), f"{name}: {field}")
              for field in ("ects", "lecture_per_week", "difficulty", "priority")}
    for field in ("ects", "lecture_per_week", "difficulty"):
        if values[field] < 0:
            raise ValueError(f"{name}: {field} cannot be negative.")
    if values["priority"] <= 0:
        raise ValueError(f"{name}: priority must be greater than 0.")
    limit = subject.get("max_study_hours")
    if limit is not None:
        limit = _number(limit, f"{name}: max_study_hours")
        if limit < 0:
            raise ValueError(f"{name}: max_study_hours cannot be negative.")
    if "examdate" not in subject:
        raise ValueError(f"{name}: an exam date is needed to plan around it.")
    return {**values, "max_study_hours": limit,
            "examdate": DayRange.from_value(subject["examdate"])}


BLOCK_TYPES = ("active_learning", "recall")


def _history(value, subjects):
    """Hours already planned before this run, so a mid-session run keeps its past."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("history must be a list of {subject, type, date, hours}.")
    entries = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Every history entry must be an object.")
        if entry.get("subject") not in subjects:
            raise ValueError(f"history mentions {entry.get('subject')!r}, which is not a subject here.")
        if entry.get("type") not in BLOCK_TYPES:
            raise ValueError(f"A history entry's type must be one of {', '.join(BLOCK_TYPES)}.")
        hours = _number(entry.get("hours"), "history: hours")
        if hours < 0:
            raise ValueError("history: hours cannot be negative.")
        entries.append({"subject": entry["subject"], "type": entry["type"],
                        "date": iso_date(entry.get("date")), "hours": hours})
    return entries


def _busy(value, subjects):
    """Time the user already filled: [{date, start_time, end_time, subject?}]."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("busy must be a list of {date, start_time, end_time}.")
    entries = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Every busy entry must be an object.")
        start = _time(entry.get("start_time"), "busy: start_time")
        end = _time(entry.get("end_time"), "busy: end_time")
        if start >= end:
            raise ValueError("A busy entry must end after it starts.")
        subject = entry.get("subject")
        if subject is not None and subject not in subjects:
            raise ValueError(f"busy mentions {subject!r}, which is not a subject here.")
        kind = entry.get("type", "active_learning" if subject is not None else "meal")
        if kind not in (*BLOCK_TYPES, "meal"):
            raise ValueError("A busy entry's type must be active_learning, recall or meal.")
        entries.append({"date": iso_date(entry.get("date")), "subject": subject,
                        "type": kind,
                        "start": int(start[:2]) * 60 + int(start[3:]), "end": int(end[:2]) * 60 + int(end[3:])})
    return entries


def validated(data):
    """Check a request and return it as the arguments Schedule takes. Never touches `data`."""
    if not isinstance(data, dict):
        raise ValueError("The scheduler input must be a JSON object.")
    subjects = data.get("subjects")
    if not isinstance(subjects, dict) or not subjects:
        raise ValueError("Add at least one subject to plan for.")
    if "exam_session" not in data:
        raise ValueError("The plan needs an exam_session to lay the weeks out in.")
    days_off = data.get("days_off", [])
    if not isinstance(days_off, (list, tuple)):
        raise ValueError("days_off must be a list of dates or date ranges.")
    exam_days_off = data.get("exam_days_off", True)
    if not isinstance(exam_days_off, bool):
        raise ValueError("exam_days_off must be true or false.")

    option = lambda field: data.get(field, DEFAULTS[field])
    day_start, day_end = _time(option("day_start"), "day_start"), _time(option("day_end"), "day_end")
    if day_start >= day_end:
        raise ValueError("day_end must be later than day_start.")
    beta = _number(option("beta"), "beta")
    if beta <= 0:
        raise ValueError("beta must be greater than 0.")

    budget = data.get("study_hours_per_week")
    if budget is not None:
        budget = _number(budget, "study_hours_per_week")
        if budget < 0:
            raise ValueError("study_hours_per_week cannot be negative.")

    prepared = {name: _subject(name, subject) for name, subject in subjects.items()}
    return {
        "subjects": prepared,
        "history": _history(data.get("history", []), prepared),
        "busy": _busy(data.get("busy", []), prepared),
        "study_hours_per_week": budget,
        "exam_session": DayRange.from_value(data["exam_session"]),
        "days_off": [DayRange.from_value(value) for value in days_off],
        "exam_days_off": exam_days_off,
        "study_block_size": _whole(option("study_block_size"), "study_block_size"),
        "day_start": day_start, "day_end": day_end,
        "lunch_time": _interval(option("lunch_time"), "lunch_time"),
        "dinner_time": _interval(option("dinner_time"), "dinner_time"),
        "alpha": _number(option("alpha"), "alpha"), "beta": beta,
        "weeks_in_semester": _whole(data.get("weeks_in_semester", WEEKS_IN_SEMESTER),
                                    "weeks_in_semester", minimum=0),
    }


def generate_schedule(data: dict) -> dict:
    """Plan every week of the exam session. Same request, same plan; `data` is left alone."""
    options = validated(data)
    planner = Schedule(
        {"subjects": options["subjects"], "days_off": options["days_off"],
         "exam_session": options["exam_session"], "study_block_size": options["study_block_size"],
         "history": options["history"], "busy": options["busy"], "exam_days_off": options["exam_days_off"]},
        options["day_start"], options["day_end"], options["lunch_time"], options["dinner_time"],
        alpha=options["alpha"], beta=options["beta"],
        weeks_in_semester=options["weeks_in_semester"],
        hours_per_week_budget=options["study_hours_per_week"])
    planner.generate_schedule()
    while planner.current_week.end_date < planner.exam_session.end_date:
        planner.next_week()
        planner.generate_schedule()
    return planner.to_dict()


def main(argv: list[str] | None = None) -> int:
    """Read a request on stdin, write the plan on stdout, errors as JSON on stderr."""
    try:
        plan = generate_schedule(json.load(sys.stdin))
    except (ValueError, TypeError) as exc:
        json.dump({"error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    json.dump(plan, sys.stdout, allow_nan=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
