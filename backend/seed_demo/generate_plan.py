"""Write a realistic study phase for the demo user into this directory's seed files.

Dev mode rebuilds the database from the seed on every start, so this is how the schedule
and the analytics views come up filled. Deterministic: the same numbers every run.

    python backend/seed_demo/generate_plan.py

Writes 07_study_hours.json and 08_study_sessions.json for Alice's HS26 semester (id 4 in
04_semesters.json, courses in 05_semester_courses.json). The story: the study phase runs
21 Dec 2026 to 14 Feb 2027; hours are recorded up to AS_OF with a slow start, a dip over
New Year and a ramp before the first exam; after AS_OF only planned sessions exist.
"""
import json
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEMESTER_ID = 4
START, END = date(2026, 12, 21), date(2027, 2, 14)
AS_OF = date(2027, 1, 20)                      # last day with recorded hours
# course_id -> (weight of the daily budget, exam date). Ids are the demo courses in 02_courses.json.
COURSES = {
    1: (0.20, date(2027, 1, 26)),   # Einführung in die Programmierung
    2: (0.35, date(2027, 2, 2)),    # Lineare Algebra
    3: (0.25, date(2027, 1, 29)),   # Diskrete Mathematik
    4: (0.20, date(2027, 2, 9)),    # Algorithmen und Datenstrukturen
}
HOLIDAYS = {date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31), date(2027, 1, 1)}


def days(first, last):
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def daily_budget(rng, day):
    """Hours available on a day: weekdays 5-8 h, weekends lighter, holidays mostly off, ramp before exams."""
    if day in HOLIDAYS:
        return 0 if rng.random() < 0.7 else rng.choice([1, 1.5])
    if rng.random() < 0.08:                      # the odd day off
        return 0
    base = rng.uniform(5, 8) if day.weekday() < 5 else rng.uniform(1.5, 4.5)
    week = (day - START).days // 7
    ramp = 1 + 0.12 * week                       # more as the exams come closer
    return round(min(10, base * ramp) * 2) / 2   # half-hour steps


def generate():
    rng = random.Random(26)
    hours, sessions = [], []
    for day in days(START, AS_OF):
        budget = daily_budget(rng, day)
        if not budget:
            continue
        # Split the budget over 1-3 courses, favouring the nearest exam and the weights.
        live = {cid: w * (1.6 if (exam - day).days < 10 else 1) for cid, (w, exam) in COURSES.items() if exam >= day}
        if not live:
            continue
        picks = rng.sample(sorted(live), k=min(len(live), rng.choice([1, 2, 2, 3])))
        total = sum(live[c] for c in picks)
        for cid in picks:
            share = round(budget * live[cid] / total * 4) / 4
            if share > 0:
                hours.append({"semester_id": SEMESTER_ID, "course_id": cid, "date": day.isoformat(), "hours": share})
    # Planned sessions: what Alice put in the calendar, from the second week on until the last
    # exam. Before AS_OF they show how well the plan was kept; after it they are the plan ahead.
    starts = ["08:15", "10:15", "13:15", "15:15", "18:00"]
    for day in days(START + timedelta(days=7), max(exam for _, exam in COURSES.values())):
        live = [cid for cid, (_, exam) in COURSES.items() if exam >= day]
        if not live or (day.weekday() == 6 and rng.random() < 0.6) or (day <= AS_OF and rng.random() < 0.3):
            continue
        slots = rng.sample(starts, k=rng.choice([1, 2, 2, 3]) if day.weekday() < 5 else 1)
        for begin in sorted(slots):
            cid = min(live, key=lambda c: (COURSES[c][1] - day).days + rng.uniform(0, 6))
            sessions.append({"semester_id": SEMESTER_ID, "id": str(uuid.UUID(int=rng.getrandbits(128))),
                             "course_id": cid, "date": day.isoformat(), "start": begin, "hours": rng.choice([1.5, 2, 2, 2.5])})
    return hours, sessions


def main():
    hours, sessions = generate()
    for name, rows in (("07_study_hours.json", hours), ("08_study_sessions.json", sessions)):
        with open(HERE / name, "w") as f:
            json.dump(rows, f, indent=2)
            f.write("\n")
    total = sum(r["hours"] for r in hours)
    print(f"{len(hours)} hour records ({total:.1f} h over {len({r['date'] for r in hours})} days), {len(sessions)} planned sessions")


if __name__ == "__main__":
    main()
