"""Tests for vvz.sync and vvz.queries against a tiny fake dump (no network)."""

import contextlib
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vvz import queries, sync  # noqa: E402

DUMP_SCHEMA = """
CREATE TABLE learningunit (id INTEGER PRIMARY KEY, semkez TEXT, number TEXT, title TEXT, title_english TEXT,
    levels JSON, credits REAL, literature TEXT, literature_english TEXT, objective TEXT, objective_english TEXT,
    content TEXT, content_english TEXT, lecture_notes TEXT, lecture_notes_english TEXT, max_places INTEGER,
    language TEXT, abstract TEXT, abstract_english TEXT, written_aids TEXT, exam_mode TEXT, exam_type TEXT,
    exam_block JSON, course_frequency TEXT, departments JSON);
CREATE TABLE course (number TEXT, semkez TEXT, unit_id INTEGER, title TEXT, type TEXT, hours REAL, hour_type TEXT,
    comment TEXT, timeslots JSON, PRIMARY KEY (number, semkez, unit_id));
CREATE TABLE lecturer (id INTEGER PRIMARY KEY, surname TEXT, name TEXT, title TEXT, department TEXT);
CREATE TABLE unitlecturerlink (unit_id INTEGER, lecturer_id INTEGER);
CREATE TABLE unitexaminerlink (unit_id INTEGER, lecturer_id INTEGER);
CREATE TABLE unitsectionlink (unit_id INTEGER, section_id INTEGER, type TEXT, type_id INTEGER);
CREATE TABLE sectionpathview (id INTEGER PRIMARY KEY, path_en TEXT, path_de TEXT);
CREATE TABLE rating (course_number TEXT PRIMARY KEY, recommended REAL, engaging REAL, difficulty REAL, effort REAL,
    resources REAL, scraped_at INTEGER);
"""

SLOTS = [
    {"weekday": 0, "date": None, "start_time": "14:15", "end_time": "16:00", "building": "HG", "floor": "F", "room": "1",
     "first_half_semester": False, "second_half_semester": False, "biweekly": False},
    {"weekday": 2, "date": None, "start_time": "10:15", "end_time": "12:00", "building": "HG", "floor": "F", "room": "1",
     "first_half_semester": False, "second_half_semester": False, "biweekly": False},
]


def unit_row(uid, semkez, number, title, title_en, credits, **extra):
    row = {"id": uid, "semkez": semkez, "number": number, "title": title, "title_english": title_en,
           "levels": '["BSC"]', "credits": credits, "language": "German", "exam_mode": "written 180 minutes",
           "exam_type": "session examination", "exam_block": "[]", "course_frequency": "ANNUAL", "departments": '["5"]'}
    row.update(extra)
    return row


def make_dump(path):
    db = sqlite3.connect(path)
    db.executescript(DUMP_SCHEMA)
    units = [
        unit_row(188507, "2025S", "401-0212-16L", "Analysis I", "Analysis I", 7.0, objective="Ziel", objective_english="Goal",
                 content="Inhalt", exam_block='["Computer Science 2016 (First Year Examination Block 2)"]'),
        unit_row(199280, "2026S", "401-0212-16L", "Analysis I", "Analysis I", 7.0, objective_english="Goal 2026"),
        unit_row(999, "2019W", "401-9999-00L", "Old course", None, 3.0),
        # Lineare Algebra: 2026W has no timeslots yet (as in the real dump), 2025W has them.
        unit_row(204074, "2026W", "401-0131-00L", "Lineare Algebra", "Linear Algebra", 7.0),
        unit_row(194000, "2025W", "401-0131-00L", "Lineare Algebra", "Linear Algebra", 7.0),
    ]
    for u in units:
        cols = ", ".join(u)
        db.execute(f"INSERT INTO learningunit ({cols}) VALUES ({', '.join('?' for _ in u)})", list(u.values()))
    db.executemany("INSERT INTO course VALUES (?,?,?,?,?,?,?,?,?)", [
        ("401-0212-16 V", "2025S", 188507, "Analysis I", "V", 4.0, "WEEKLY_HOURS", None, json.dumps(SLOTS)),
        ("401-0212-16 U", "2025S", 188507, "Analysis I", "U", 2.0, "WEEKLY_HOURS", "Groups", json.dumps(SLOTS[:1])),
        ("401-0212-16 V", "2026S", 199280, "Analysis I", "V", 4.0, "WEEKLY_HOURS", None, json.dumps(SLOTS[:1])),
        ("401-9999-00 V", "2019W", 999, "Old", "V", 2.0, "WEEKLY_HOURS", None, "[]"),
        ("401-0131-00 V", "2026W", 204074, "Lineare Algebra", "V", 4.0, "WEEKLY_HOURS", None, "null"),
        ("401-0131-00 V", "2025W", 194000, "Lineare Algebra", "V", 4.0, "WEEKLY_HOURS", None, json.dumps(SLOTS[1:])),
    ])
    db.execute("INSERT INTO lecturer VALUES (?,?,?,?,?)", (1, "Imamoglu", "Özlem", "Prof. Dr.", "Mathematik"))
    db.execute("INSERT INTO lecturer VALUES (?,?,?,?,?)", (2, "Nobody", "Not", None, "Linked"))
    db.execute("INSERT INTO unitlecturerlink VALUES (188507, 1)")
    db.execute("INSERT INTO unitexaminerlink VALUES (188507, 1)")
    db.execute("INSERT INTO unitsectionlink VALUES (188507, 17673, 'O', 1)")
    db.execute("INSERT INTO sectionpathview VALUES (17673, 'Computer Science Bachelor > 2. Semester Bachelor Programme > First Year Examinations (2. Sem.)', 'Informatik Bachelor > 2. Semester')")
    db.execute("INSERT INTO rating VALUES ('401-0212-16L', 2.5, 2.5, 3.5, 3.5, 3.5, 0)")
    db.commit()
    db.close()


class SemesterMathTest(unittest.TestCase):
    def test_semester_of(self):
        self.assertEqual(sync.semester_of(dt.date(2026, 10, 10)), "2026W")
        self.assertEqual(sync.semester_of(dt.date(2027, 1, 15)), "2026W")
        self.assertEqual(sync.semester_of(dt.date(2027, 3, 1)), "2027S")

    def test_shift_and_default_window(self):
        self.assertEqual(sync.shift_semester("2026W", 1), "2027S")
        self.assertEqual(sync.shift_semester("2026W", -1), "2026S")
        self.assertEqual(sync.default_semesters(dt.date(2026, 10, 10)), ["2026S", "2026W", "2027S", "2027W"])
        self.assertEqual((sync.term_of("2026W"), sync.term_of("2027S")), ("HS", "FS"))

    def test_configured_semesters_from_arg(self):
        self.assertEqual(sync.configured_semesters("2025w, 2026S"), ["2025W", "2026S"])


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dump = os.path.join(self.tmp.name, "database.db")
        self.db = os.path.join(self.tmp.name, "data", "app.db")
        make_dump(self.dump)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_filters_semesters_and_fills_every_table(self):
        counts = sync.import_dump(self.dump, self.db, ["2025S"], meta={"dump_last_modified_ms": "123"})
        self.assertEqual(counts, {"courses": 1, "offerings": 1, "lectures": 2, "timeslots": 3,
                                  "inherited_timeslots": 0, "lecturers": 1, "sections": 1})

        [course] = queries.search_courses("analysis", db_path=self.db)
        self.assertEqual((course["code"], course["ects"], course["term"], course["offering_id"]), ("401-0212-16L", 7, "FS", 188507))
        self.assertEqual(course["professor"], "Prof. Dr. Özlem Imamoglu")
        full = queries.get_course(course["id"], db_path=self.db)
        self.assertEqual(full["objective"], "Goal")   # English preferred
        self.assertEqual(full["content"], "Inhalt")   # German fallback
        self.assertEqual(full["exam_block"], ["Computer Science 2016 (First Year Examination Block 2)"])
        self.assertEqual(full["weekly_hours"], 6.0)
        self.assertEqual(full["rating"]["difficulty"], 3.5)
        self.assertEqual(full["offered_in"], ["2025S"])
        offering = full["offering"]
        self.assertEqual((offering["id"], offering["semkez"], offering["weekly_hours"]), (188507, "2025S", 6.0))
        lecture = next(l for l in offering["lectures"] if l["type"] == "V")
        self.assertEqual(lecture["type_name"], "lecture")
        self.assertEqual([s["weekday_name"] for s in lecture["timeslots"]], ["Mon", "Wed"])
        self.assertEqual(lecture["timeslots"][0]["building"], "HG")
        self.assertIsNone(lecture["timeslots"][0]["inherited_from"])
        self.assertEqual({(l["surname"], l["role"]) for l in offering["lecturers"]}, {("Imamoglu", "lecturer"), ("Imamoglu", "examiner")})
        self.assertIn("Computer Science Bachelor", offering["sections"][0]["path_en"])

        self.assertEqual(queries.search_courses("Old", db_path=self.db), [])
        self.assertEqual(queries.semesters(db_path=self.db), ["2025S"])
        self.assertEqual(queries.status(db_path=self.db)["dump_last_modified_ms"], "123")

    def test_courses_are_upserted_by_code_and_keep_their_id(self):
        sync.import_dump(self.dump, self.db, ["2025S"])
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO courses (id, code, title, term, ects, professor) VALUES (42, '401-0131-00L', 'Linear Algebra', 'HS', 9, 'Prof. Example')")
            db.execute("INSERT INTO users (id, email) VALUES (1, 'a@ethz.ch')")
            db.execute("INSERT INTO semesters (id, user_id, label) VALUES (1, 1, 'HS26')")
            db.execute("INSERT INTO semester_courses (semester_id, course_id) VALUES (1, 42)")
            [(analysis_id,)] = db.execute("SELECT id FROM courses WHERE code = '401-0212-16L'").fetchall()
            db.commit()

        counts = sync.import_dump(self.dump, self.db, ["2025S", "2026S", "2026W"])
        self.assertEqual((counts["courses"], counts["offerings"]), (2, 3))
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            rows = {r[0]: r[1:] for r in db.execute("SELECT code, id, ects, professor, latest_semkez FROM courses")}
        self.assertEqual(rows["401-0131-00L"], (42, 7, "Prof. Example", "2026W"))      # id kept, ects fixed, professor kept
        self.assertEqual(rows["401-0212-16L"][0], analysis_id)
        self.assertEqual(rows["401-0212-16L"][3], "2026S")                             # the latest offering wins
        full = queries.get_course(analysis_id, db_path=self.db)
        self.assertEqual((full["objective"], full["offered_in"], full["offering"]["semkez"]), ("Goal 2026", ["2025S", "2026S"], "2026S"))
        self.assertEqual(queries.get_course(analysis_id, semkez="2025S", db_path=self.db)["offering"]["id"], 188507)

        # Re-importing is idempotent: offerings are replaced, nothing doubles.
        sync.import_dump(self.dump, self.db, ["2025S", "2026S", "2026W"])
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM course_offerings").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM course_timeslots").fetchone()[0], 5)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM semester_courses").fetchone()[0], 1)

    def test_missing_timeslots_are_inherited_from_previous_year(self):
        counts = sync.import_dump(self.dump, self.db, ["2026W"])
        self.assertEqual((counts["offerings"], counts["timeslots"], counts["inherited_timeslots"]), (1, 0, 1))
        [course] = queries.search_courses(semkez="2026W", db_path=self.db)
        lecture = queries.get_course(course["id"], db_path=self.db)["offering"]["lectures"][0]
        self.assertEqual(lecture["number"], "401-0131-00 V")
        self.assertEqual(len(lecture["timeslots"]), 1)
        self.assertEqual(lecture["timeslots"][0]["inherited_from"], "2025W")
        self.assertEqual(lecture["timeslots"][0]["weekday_name"], "Wed")
        self.assertEqual(queries.weekly_timetable([course["id"]], "2026W", db_path=self.db)[0]["inherited_from"], "2025W")

    def test_search_filters(self):
        sync.import_dump(self.dump, self.db, ["2025S", "2026W"])
        self.assertEqual([c["code"] for c in queries.search_courses(semkez="2025S", db_path=self.db)], ["401-0212-16L"])
        self.assertEqual([c["code"] for c in queries.search_courses(section="Computer Science Bachelor", db_path=self.db)], ["401-0212-16L"])
        self.assertEqual([c["code"] for c in queries.search_courses(db_path=self.db)], ["401-0131-00L", "401-0212-16L"])
        self.assertEqual(queries.search_courses("Lineare", semkez="2025S", db_path=self.db), [])

    def test_sync_offline_without_cache_is_a_noop_and_dump_path_imports(self):
        self.assertFalse(sync.sync(offline=True, semesters=["2025S"], db_path=self.db, data_dir=self.tmp.name))
        self.assertTrue(sync.sync(semesters=["2025S"], dump_path=self.dump, db_path=self.db, data_dir=self.tmp.name))
        self.assertEqual(queries.status(db_path=self.db)["semesters"], "2025S")

    def test_a_unit_listed_twice_in_one_semester_becomes_one_offering(self):
        with contextlib.closing(sqlite3.connect(self.dump)) as dump:
            dump.execute("INSERT INTO learningunit (id, semkez, number, title, credits) VALUES (204999, '2026W', '401-0131-00L', 'Lineare Algebra', 7.0)")
            dump.execute("INSERT INTO course VALUES ('401-0131-00 V', '2026W', 204999, 'Lineare Algebra', 'V', 4.0, 'WEEKLY_HOURS', NULL, 'null')")
            dump.commit()
        counts = sync.import_dump(self.dump, self.db, ["2026W"])
        self.assertEqual((counts["courses"], counts["offerings"]), (1, 1))
        [course] = queries.search_courses(semkez="2026W", db_path=self.db)
        self.assertEqual(queries.get_course(course["id"], db_path=self.db)["offering"]["id"], 204999)

    def test_import_rejects_empty_semesters(self):
        with self.assertRaises(ValueError):
            sync.import_dump(self.dump, self.db, [])


if __name__ == "__main__":
    unittest.main()
