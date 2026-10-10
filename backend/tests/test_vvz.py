"""Tests for vvz.sync and vvz.queries against a tiny fake dump (no network)."""

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


def make_dump(path):
    db = sqlite3.connect(path)
    db.executescript(DUMP_SCHEMA)
    db.execute(
        "INSERT INTO learningunit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (188507, "2025S", "401-0212-16L", "Analysis I", "Analysis I", '["BSC"]', 7.0, None, None, "Ziel", "Goal",
         "Inhalt", None, None, None, None, "German", None, None, None, "written 180 minutes", "session examination",
         '["Computer Science 2016 (First Year Examination Block 2)"]', "ANNUAL", '["5"]'),
    )
    db.execute(
        "INSERT INTO learningunit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (999, "2019W", "401-9999-00L", "Old course", None, "[]", 3.0, None, None, None, None, None, None, None, None,
         None, None, None, None, None, None, None, "[]", None, "[]"),
    )
    db.execute("INSERT INTO course VALUES (?,?,?,?,?,?,?,?,?)",
               ("401-0212-16 V", "2025S", 188507, "Analysis I", "V", 4.0, "WEEKLY_HOURS", None, json.dumps(SLOTS)))
    db.execute("INSERT INTO course VALUES (?,?,?,?,?,?,?,?,?)",
               ("401-0212-16 U", "2025S", 188507, "Analysis I", "U", 2.0, "WEEKLY_HOURS", "Groups", json.dumps(SLOTS[:1])))
    db.execute("INSERT INTO course VALUES (?,?,?,?,?,?,?,?,?)",
               ("401-9999-00 V", "2019W", 999, "Old", "V", 2.0, "WEEKLY_HOURS", None, "[]"))
    # Lineare Algebra: 2026W has no timeslots yet (as in the real dump), 2025W has them.
    for uid, semkez in ((204074, "2026W"), (194000, "2025W")):
        db.execute(
            "INSERT INTO learningunit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, semkez, "401-0131-00L", "Lineare Algebra", "Linear Algebra", '["BSC"]', 7.0, None, None, None, None,
             None, None, None, None, None, "German", None, None, None, "written 180 minutes", "session examination",
             "[]", "ANNUAL", '["5"]'),
        )
    db.execute("INSERT INTO course VALUES (?,?,?,?,?,?,?,?,?)",
               ("401-0131-00 V", "2026W", 204074, "Lineare Algebra", "V", 4.0, "WEEKLY_HOURS", None, "null"))
    db.execute("INSERT INTO course VALUES (?,?,?,?,?,?,?,?,?)",
               ("401-0131-00 V", "2025W", 194000, "Lineare Algebra", "V", 4.0, "WEEKLY_HOURS", None, json.dumps(SLOTS[1:])))
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

    def test_configured_semesters_from_arg(self):
        self.assertEqual(sync.configured_semesters("2025w, 2026S"), ["2025W", "2026S"])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dump = os.path.join(self.tmp.name, "database.db")
        self.db = os.path.join(self.tmp.name, "out", "vvz.db")
        make_dump(self.dump)

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_filters_semesters_and_copies_everything(self):
        counts = sync.build_db(self.dump, self.db, ["2025S"], meta={"dump_last_modified_ms": "123"})
        self.assertEqual(counts, {"units": 1, "courses": 2, "timeslots": 3, "lecturers": 1, "sections": 1, "inherited_timeslots": 0})
        self.assertFalse(os.path.exists(self.db + ".building"))

        unit = queries.get_unit(188507, db_path=self.db)
        self.assertEqual(unit["credits"], 7.0)
        self.assertEqual(unit["weekly_hours"], 6.0)
        self.assertEqual(unit["objective"], "Goal")   # English preferred
        self.assertEqual(unit["content"], "Inhalt")   # German fallback
        self.assertEqual(unit["exam_block"], ["Computer Science 2016 (First Year Examination Block 2)"])
        lecture = next(c for c in unit["courses"] if c["type"] == "V")
        self.assertEqual(lecture["type_name"], "lecture")
        self.assertEqual([s["weekday_name"] for s in lecture["timeslots"]], ["Mon", "Wed"])
        self.assertEqual(lecture["timeslots"][0]["building"], "HG")
        self.assertIsNone(lecture["timeslots"][0]["inherited_from"])
        self.assertEqual({(l["surname"], l["role"]) for l in unit["lecturers"]}, {("Imamoglu", "lecturer"), ("Imamoglu", "examiner")})
        self.assertIn("Computer Science Bachelor", unit["sections"][0]["path_en"])
        self.assertEqual(unit["rating"]["difficulty"], 3.5)

        self.assertIsNone(queries.get_unit(999, db_path=self.db))
        self.assertEqual(queries.semesters(db_path=self.db), ["2025S"])
        self.assertEqual(queries.status(db_path=self.db)["dump_last_modified_ms"], "123")

    def test_search_and_timetable(self):
        sync.build_db(self.dump, self.db, ["2025S", "2019W"])
        hits = queries.search_units("analysis", semkez="2025S", db_path=self.db)
        self.assertEqual([h["number"] for h in hits], ["401-0212-16L"])
        self.assertEqual(queries.search_units(section="Computer Science Bachelor", db_path=self.db)[0]["id"], 188507)
        self.assertEqual(queries.search_units("Old", db_path=self.db)[0]["semkez"], "2019W")
        slots = queries.weekly_timetable([188507], db_path=self.db)
        self.assertEqual(len(slots), 3)
        self.assertEqual((slots[0]["weekday"], slots[0]["start_time"]), (0, "14:15"))
        self.assertEqual({s["type"] for s in slots}, {"V", "U"})
        self.assertTrue(all(s["unit_number"] == "401-0212-16L" for s in slots))

    def test_sync_from_local_dump_and_missing_db(self):
        with self.assertRaises(queries.NotSynced):
            queries.status(db_path=self.db)
        self.assertTrue(sync.sync(semesters=["2025S"], dump_path=self.dump, db_path=self.db))
        self.assertEqual(queries.status(db_path=self.db)["semesters"], "2025S")

    def test_missing_timeslots_are_inherited_from_previous_year(self):
        counts = sync.build_db(self.dump, self.db, ["2026W"])
        self.assertEqual((counts["units"], counts["timeslots"], counts["inherited_timeslots"]), (1, 0, 1))  # real slots vs inherited
        unit = queries.get_unit(204074, db_path=self.db)
        lecture = unit["courses"][0]
        self.assertEqual(lecture["number"], "401-0131-00 V")
        self.assertEqual(len(lecture["timeslots"]), 1)
        self.assertEqual(lecture["timeslots"][0]["inherited_from"], "2025W")
        self.assertEqual(lecture["timeslots"][0]["weekday_name"], "Wed")
        self.assertEqual(queries.weekly_timetable([204074], db_path=self.db)[0]["inherited_from"], "2025W")

    def test_build_rejects_empty_semesters(self):
        with self.assertRaises(ValueError):
            sync.build_db(self.dump, self.db, [])


if __name__ == "__main__":
    unittest.main()
