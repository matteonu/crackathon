"""Write realistic study phases for the demo user into this directory's seed files.

Dev mode rebuilds the database from the seed on every start, so this is how the schedule and
the analytics views come up filled, for the current semester and the two before it (the
sidebar's semester picker switches between them). Deterministic: the same numbers every run.

    python backend/seed_demo/generate_plan.py

Owns Alice's rows in 04_semesters.json, 05_semester_courses.json and 06_statistics.json
(Bob's are left alone), adds the courses it needs to 02_courses.json, and writes
07_study_hours.json and 08_study_sessions.json. The VVZ sync later upserts the courses by
code, so their ids are stable and their titles and ECTS get corrected from the catalogue.

The story, a CS student:
  HS25  first-year autumn, a rough start: erratic days, under target, little planning.
  FS26  first-year spring, found a rhythm: steady hours, target reached, plan mostly kept.
  HS26  second-year autumn, in progress: recorded up to AS_OF, sessions planned beyond.
"""
import json
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALICE = 1

# code -> (id, term, ects, title). Ids 1-5 predate this script; the rest are appended by it.
COURSES = {
    "252-0027-00L": (1, "HS", 7, "Introduction to Programming"),
    "401-0131-00L": (2, "HS", 7, "Linear Algebra"),
    "252-0025-01L": (3, "HS", 7, "Discrete Mathematics"),
    "252-0026-00L": (4, "HS", 7, "Algorithms and Data Structures"),
    "401-0212-16L": (5, "FS", 7, "Analysis I"),
    "252-0029-00L": (6, "FS", 7, "Parallel Programming"),
    "252-0030-00L": (7, "FS", 7, "Algorithms and Probability"),
    "401-0614-00L": (8, "FS", 5, "Probability and Statistics"),
    "252-0057-00L": (9, "HS", 7, "Theoretical Computer Science"),
    "252-0061-00L": (10, "HS", 7, "Systems Programming and Computer Architecture"),
    "401-0663-00L": (11, "HS", 7, "Numerical Methods for Computer Science"),
    "401-0213-16L": (12, "HS", 5, "Analysis II"),
}
COLORS = ["#2598A2", "#E4AC17", "#D56568", "#5586CA", "#DD792F", "#6E9A5A", "#9A6BB8", "#C2577E"]


def course(cid, weight, exam, target, grade, action):
    return {"id": cid, "weight": weight, "exam": exam, "target": target, "grade": grade, "action": action}


# One entry per semester. `as_of` is the last day with recorded hours; past phases are complete.
SEMESTERS = [
    {
        "id": 1, "label": "HS25", "hours_per_week": 20, "seed": 25,
        "start": date(2025, 12, 21), "end": date(2026, 2, 14), "as_of": date(2026, 2, 14),
        "profile": {"weekday": (3, 7), "weekend": (0, 3), "off": 0.22, "ramp": 0.10, "plan_days": 0.35, "keep": 0.55, "rest": 0.2},
        "holidays": {date(2025, 12, 24), date(2025, 12, 25), date(2025, 12, 31), date(2026, 1, 1)},
        "courses": [
            course(1, 0.25, date(2026, 1, 27), 60, 4.5, "Go through the recursion exercises again"),
            course(2, 0.30, date(2026, 2, 3), 90, 4.0, "Old exams: eigenvalues and diagonalisation"),
            course(3, 0.25, date(2026, 1, 30), 70, 4.5, "Rewrite the proof-techniques summary"),
            course(4, 0.20, date(2026, 2, 10), 70, 4.0, "Dynamic programming sheet, exercises 3-6"),
        ],
    },
    {
        "id": 2, "label": "FS26", "hours_per_week": 25, "seed": 26,
        "start": date(2026, 6, 1), "end": date(2026, 8, 31), "as_of": date(2026, 8, 31),
        "profile": {"weekday": (2.5, 5), "weekend": (1, 3), "off": 0.10, "ramp": 0.03, "plan_days": 0.75, "keep": 0.85, "rest": 0.8},
        "holidays": {date(2026, 8, 1)},
        "courses": [
            course(5, 0.35, date(2026, 8, 11), 110, 5.0, "Series and uniform convergence, old exam 2024"),
            course(6, 0.20, date(2026, 8, 18), 60, 5.5, "Locks and condition variables, lecture 9"),
            course(7, 0.25, date(2026, 8, 21), 75, 5.0, "Randomised algorithms: Karger and hashing"),
            course(8, 0.20, date(2026, 8, 26), 50, 5.0, "Estimators and confidence intervals"),
        ],
    },
    {
        "id": 4, "label": "HS26", "hours_per_week": 30, "seed": 27,
        "start": date(2026, 12, 21), "end": date(2027, 2, 14), "as_of": date(2027, 1, 20),
        "profile": {"weekday": (5, 8), "weekend": (1.5, 4.5), "off": 0.08, "ramp": 0.12, "plan_days": 0.7, "keep": 0.75, "rest": 0.6},
        "holidays": {date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31), date(2027, 1, 1)},
        "courses": [
            course(9, 0.30, date(2027, 1, 28), 90, 5.0, "Pumping lemma and reductions, exercises 7-9"),
            course(10, 0.25, date(2027, 2, 2), 70, 4.5, "Caches and virtual memory, redo the lab"),
            course(11, 0.25, date(2027, 1, 25), 70, 5.0, "Least squares and QR, old exam 2025"),
            course(12, 0.20, date(2027, 2, 9), 55, 4.5, "Multivariable integrals, sheet 10"),
        ],
    },
]


def days(first, last):
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def daily_budget(rng, day, semester):
    """Hours available on a day, from the semester's profile: lighter weekends and holidays,
    the odd day off, and a ramp as the exams come closer. Half-hour steps."""
    profile = semester["profile"]
    if day in semester["holidays"]:
        return 0 if rng.random() < 0.7 else rng.choice([1, 1.5])
    if rng.random() < profile["off"]:
        return 0
    low, high = profile["weekday"] if day.weekday() < 5 else profile["weekend"]
    week = (day - semester["start"]).days // 7
    return round(min(10, rng.uniform(low, high) * (1 + profile["ramp"] * week)) * 2) / 2


def generate(semester):
    rng = random.Random(semester["seed"])
    sid, courses, profile = semester["id"], semester["courses"], semester["profile"]
    exam_of = {c["id"]: c["exam"] for c in courses}
    weight_of = {c["id"]: c["weight"] for c in courses}
    hours, sessions = [], []

    # Planned sessions first: from the second week until the last exam, on `plan_days` of the
    # days. Before as_of they measure how well the plan was kept; after it they are the plan ahead.
    starts = ["08:15", "10:15", "13:15", "15:15", "18:00"]
    planned_by_day = {}
    for day in days(semester["start"] + timedelta(days=7), max(exam_of.values())):
        live = [cid for cid in exam_of if exam_of[cid] >= day]
        if not live or rng.random() > (profile["plan_days"] * (0.5 if day.weekday() == 6 else 1)):
            continue
        for begin in sorted(rng.sample(starts, k=rng.choice([1, 2, 2, 3]) if day.weekday() < 5 else 1)):
            cid = min(live, key=lambda c: (exam_of[c] - day).days + rng.uniform(0, 6))
            length = rng.choice([1.5, 2, 2, 2.5])
            sessions.append({"semester_id": sid, "id": str(uuid.UUID(int=rng.getrandbits(128))),
                             "course_id": cid, "date": day.isoformat(), "start": begin, "hours": length})
            planned_by_day.setdefault(day, []).append((cid, length))

    # Recorded hours up to as_of. A planned day is kept with probability `keep` (then the plan's
    # subjects get the time); otherwise the day's budget is split over 1-3 live courses.
    for day in days(semester["start"], semester["as_of"]):
        budget = daily_budget(rng, day, semester)
        live = {cid: weight_of[cid] * (1.6 if (exam_of[cid] - day).days < 10 else 1) for cid in exam_of if exam_of[cid] >= day}
        if not live:
            continue
        if not budget and rng.random() < profile["rest"]:
            # A deliberate day off, recorded as 0 (the schedule's rest-day marker): the
            # streak survives it, a day with no record at all does not.
            hours.append({"semester_id": sid, "course_id": min(live), "date": day.isoformat(), "hours": 0})
            continue
        if day in planned_by_day and rng.random() < profile["keep"]:
            shares = {}
            for cid, length in planned_by_day[day]:
                shares[cid] = shares.get(cid, 0) + length * rng.choice([0.75, 1, 1, 1.25])
            split = shares
        elif budget:
            picks = rng.sample(sorted(live), k=min(len(live), rng.choice([1, 2, 2, 3])))
            total = sum(live[c] for c in picks)
            split = {cid: budget * live[cid] / total for cid in picks}
        else:
            continue
        for cid, value in split.items():
            share = round(value * 4) / 4
            if share > 0:
                hours.append({"semester_id": sid, "course_id": cid, "date": day.isoformat(), "hours": share})
        # Keep a day's total within what the API allows.
        total = sum(h["hours"] for h in hours if h["date"] == day.isoformat())
        if total > 14:
            for h in hours:
                if h["date"] == day.isoformat():
                    h["hours"] = round(h["hours"] * 14 / total * 4) / 4
    return hours, sessions


def load(name):
    with open(HERE / name) as f:
        return json.load(f)


def save(name, rows):
    with open(HERE / name, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    # Courses: add the ones this script uses, by code.
    courses = load("02_courses.json")
    known = {c["code"] for c in courses}
    for code, (cid, term, ects, title) in COURSES.items():
        if code not in known:
            courses.append({"id": cid, "code": code, "title": title, "term": term, "ects": ects, "professor": None})
    save("02_courses.json", sorted(courses, key=lambda c: c["id"]))

    mine = {s["id"] for s in SEMESTERS}
    semesters = [s for s in load("04_semesters.json") if s["id"] not in mine]
    semesters += [{"id": s["id"], "user_id": ALICE, "label": s["label"], "study_hours_per_week": s["hours_per_week"]} for s in SEMESTERS]
    save("04_semesters.json", sorted(semesters, key=lambda s: s["id"]))

    semester_courses = [r for r in load("05_semester_courses.json") if r["semester_id"] not in mine]
    for s in SEMESTERS:
        for i, c in enumerate(s["courses"]):
            semester_courses.append({"semester_id": s["id"], "course_id": c["id"], "desired_grade": c["grade"],
                                     "target_hours": c["target"], "exam_date": c["exam"].isoformat(),
                                     "completed": int(s["as_of"] >= c["exam"]), "color": COLORS[i % len(COLORS)],
                                     "next_action": "" if s["as_of"] >= c["exam"] else c["action"]})
    save("05_semester_courses.json", sorted(semester_courses, key=lambda r: (r["semester_id"], r["course_id"])))

    statistics = [r for r in load("06_statistics.json") if r["semester_id"] not in mine]
    statistics += [{"user_id": ALICE, "semester_id": s["id"]} for s in SEMESTERS]
    save("06_statistics.json", sorted(statistics, key=lambda r: (r["user_id"], r["semester_id"])))

    all_hours, all_sessions = [], []
    for s in SEMESTERS:
        hours, sessions = generate(s)
        all_hours += hours
        all_sessions += sessions
        total = sum(h["hours"] for h in hours)
        target = sum(c["target"] for c in s["courses"])
        print(f"{s['label']}: {len(hours)} hour records, {total:.0f} of {target} target hours over "
              f"{len({h['date'] for h in hours})} days, {len(sessions)} planned sessions")
    save("07_study_hours.json", all_hours)
    save("08_study_sessions.json", all_sessions)


if __name__ == "__main__":
    main()
