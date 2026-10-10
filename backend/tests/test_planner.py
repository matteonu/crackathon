"""Adding VVZ courses to the caller's semester: /api/semesters and /api/courses."""
import tempfile
import unittest
from unittest.mock import patch

import db
from tests.support import build_app

ALICE = {"X-User-Id": "alice@ethz.ch", "X-User-Name": "Alice"}
BOB = {"X-User-Id": "bob@ethz.ch", "X-User-Name": "Bob"}


def add_catalogue(app):
    """A tiny catalogue: two courses in 2026W, one of them also in 2027S, one only in 2027S."""
    with app.app_context():
        conn = db.get_db()
        with conn:
            conn.executemany("INSERT INTO courses (id, code, title, title_english, ects, professor, levels) VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (1, "252-0026-00L", "Algorithmen und Datenstrukturen", "Algorithms and Data Structures", 7, "Old Name", '["BSC"]'),
                (2, "401-0131-00L", "Lineare Algebra", "Linear Algebra", 7, None, '["BSC"]'),
                (3, "252-0030-00L", "Algorithmen und Wahrscheinlichkeit", "Algorithms and Probability", 7, None, '["BSC"]'),
                (4, "252-0099-00L", "100% Wildcard_Test", None, 3, None, None),
            ])
            conn.executemany("INSERT INTO course_offerings (id, course_id, semkez, title, ects, weekly_hours) VALUES (?, ?, ?, ?, ?, ?)", [
                (900, 1, "2026W", "Algorithms and Data Structures", 7, 6),
                (901, 2, "2026W", "Linear Algebra", 7, 6),
                (902, 3, "2027S", "Algorithms and Probability", 7, 6),
                (903, 2, "2027S", "Linear Algebra", 7, 6),
                (904, 4, "2026W", "100% Wildcard_Test", 3, 2),
            ])
            conn.execute("INSERT INTO lecturers (id, title, name, surname) VALUES (1, 'Prof. Dr.', 'Ada', 'Lovelace')")
            conn.execute("INSERT INTO course_lecturers (offering_id, lecturer_id, role) VALUES (900, 1, 'lecturer')")


class PlannerCase(unittest.TestCase):
    """An app with the tiny catalogue, two users, and "today" in HS26."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = build_app(self.tmp.name)
        add_catalogue(self.app)
        self.client = self.app.test_client()
        today = patch("planner.semester_of", return_value="2026W")
        today.start()
        self.addCleanup(today.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, path, user=ALICE):
        return self.client.get(path, headers=user)

    def add(self, course_id, semkez="2026W", user=ALICE):
        return self.client.post(f"/api/semesters/{semkez}/courses", json={"courseId": course_id}, headers=user)


class PlannerTests(PlannerCase):

    def test_semesters_lists_current_and_available(self):
        body = self.get("/api/semesters").get_json()
        self.assertEqual(body["current"], "2026W")
        self.assertEqual(body["available"], [{"semkez": "2026W", "label": "HS26", "inCatalogue": True},
                                             {"semkez": "2027S", "label": "FS27", "inCatalogue": True}])
        self.assertEqual(body["selected"], "2026W")   # nothing chosen yet: the current semester
        self.assertEqual(body["mine"], [])

    def test_current_falls_back_to_the_latest_imported_semester(self):
        with patch("planner.semester_of", return_value="2030W"):
            self.assertEqual(self.get("/api/semesters").get_json()["current"], "2027S")

    def test_search_matches_code_and_title_in_that_semester_only(self):
        titles = [c["title"] for c in self.get("/api/courses?q=algorithm&semkez=2026W").get_json()]
        self.assertEqual(titles, ["Algorithms and Data Structures"])   # Algorithms and Probability is 2027S only
        hit = self.get("/api/courses?q=252-0026&semkez=2026W").get_json()[0]
        self.assertEqual((hit["code"], hit["ects"], hit["professor"], hit["levels"], hit["added"]),
                         ("252-0026-00L", 7, "Prof. Dr. Ada Lovelace", ["BSC"], False))
        self.assertEqual(len(self.get("/api/courses?q=algorithm&semkez=2027S").get_json()), 1)

    def test_search_treats_percent_and_underscore_literally(self):
        self.assertEqual([c["code"] for c in self.get("/api/courses?q=100%25&semkez=2026W").get_json()], ["252-0099-00L"])
        self.assertEqual([c["code"] for c in self.get("/api/courses?q=d_t&semkez=2026W").get_json()], ["252-0099-00L"])

    def test_search_needs_a_query_and_a_known_semester(self):
        self.assertEqual(self.get("/api/courses?q=a&semkez=2026W").status_code, 400)
        self.assertEqual(self.get("/api/courses?q=algebra&semkez=2019W").status_code, 400)
        self.assertEqual(self.get("/api/courses?q=algebra&semkez=nonsense").status_code, 400)

    def test_add_list_and_remove(self):
        response = self.add(1)
        self.assertEqual(response.status_code, 201)
        entry = response.get_json()
        self.assertEqual((entry["code"], entry["title"], entry["ects"], entry["professor"], entry["term"], entry["offeringId"]),
                         ("252-0026-00L", "Algorithms and Data Structures", 7, "Prof. Dr. Ada Lovelace", "HS", 900))
        self.assertIn("lerneinheitId=900", entry["vvzUrl"])
        # The semester row was created on the first add.
        with self.app.app_context():
            self.assertEqual([r["label"] for r in db.get_db().execute("SELECT label FROM semesters")], ["HS26"])

        self.assertEqual([c["code"] for c in self.get("/api/semesters/2026W/courses").get_json()], ["252-0026-00L"])
        self.assertTrue(self.get("/api/courses?q=algorithms&semkez=2026W").get_json()[0]["added"])
        self.assertEqual(self.get("/api/semesters").get_json()["mine"],
                         [{"semkez": "2026W", "label": "HS26", "courseCount": 1, "ectsTotal": 7}])

        self.assertEqual(self.client.delete("/api/semesters/2026W/courses/1", headers=ALICE).status_code, 200)
        self.assertEqual(self.get("/api/semesters/2026W/courses").get_json(), [])
        self.assertEqual(self.client.delete("/api/semesters/2026W/courses/1", headers=ALICE).status_code, 404)

    def test_add_rejects_duplicates_and_courses_not_offered(self):
        self.assertEqual(self.add(1).status_code, 201)
        self.assertEqual(self.add(1).status_code, 409)
        not_offered = self.add(3)   # 2027S only
        self.assertEqual((not_offered.status_code, not_offered.get_json()["error"]),
                         (400, "This course is not offered in HS26."))
        self.assertEqual(self.add(999).status_code, 400)
        self.assertEqual(self.client.post("/api/semesters/2026W/courses", json={"courseId": "1"}, headers=ALICE).status_code, 400)
        self.assertEqual(self.add(1, semkez="2019W").status_code, 400)

    def test_semesters_are_separate(self):
        self.add(2, "2026W")
        self.add(2, "2027S")
        self.assertEqual([c["code"] for c in self.get("/api/semesters/2027S/courses").get_json()], ["401-0131-00L"])
        self.assertEqual(self.client.delete("/api/semesters/2027S/courses/2", headers=ALICE).status_code, 200)
        self.assertEqual(len(self.get("/api/semesters/2026W/courses").get_json()), 1)

    def test_users_only_see_their_own_courses(self):
        self.add(1)
        self.assertEqual(self.get("/api/semesters/2026W/courses", user=BOB).get_json(), [])
        self.assertFalse(self.get("/api/courses?q=algorithms&semkez=2026W", user=BOB).get_json()[0]["added"])
        self.assertEqual(self.client.delete("/api/semesters/2026W/courses/1", headers=BOB).status_code, 404)
        self.assertEqual(len(self.get("/api/semesters/2026W/courses").get_json()), 1)

    def test_needs_a_user(self):
        for path in ("/api/semesters", "/api/semesters/2026W/courses", "/api/courses?q=algebra&semkez=2026W"):
            self.assertEqual(self.client.get(path).status_code, 401, path)


class PlanTests(PlannerCase):
    """The study plan of a semester: subjects, recorded hours and planned sessions."""

    def plan(self, user=ALICE):
        return self.get("/api/semesters/2026W/plan", user=user).get_json()

    def patch(self, body, course_id=1, user=ALICE):
        return self.client.patch(f"/api/semesters/2026W/courses/{course_id}", json=body, headers=user)

    def hours(self, date, hours, course_id=1, user=ALICE):
        return self.client.put(f"/api/semesters/2026W/courses/{course_id}/hours/{date}", json={"hours": hours}, headers=user)

    def sessions(self, sessions, user=ALICE):
        return self.client.put("/api/semesters/2026W/sessions", json=sessions, headers=user)

    def test_an_empty_plan_has_the_study_phase(self):
        self.assertEqual(self.plan(), {"semkez": "2026W", "label": "HS26", "start": "2026-12-21", "end": "2027-02-14",
                                       "subjects": [], "sessions": []})
        self.assertEqual(self.get("/api/semesters/2027S/plan").get_json()["start"], "2027-06-01")

    def test_an_added_course_is_a_subject_with_defaults(self):
        self.add(1)
        self.add(2)
        first, second = self.plan()["subjects"]
        self.assertEqual(first, {
            "id": "course-1", "courseId": 1, "name": "Algorithms and Data Structures",
            "shortName": "Algorithms and Data Structures", "color": "#2598A2", "targetHours": 0,
            "examDate": "2027-02-14", "completed": False, "nextAction": "", "ects": 7,
            "lectureId": "252-0026-00L", "homepage": first["homepage"], "desiredGrade": None, "hours": {}})
        self.assertIn("lerneinheitId=900", first["homepage"])
        self.assertEqual(second["color"], "#E4AC17")   # the next colour

    def test_update_a_subject(self):
        self.add(1)
        response = self.patch({"targetHours": 65.5, "examDate": "2027-01-28", "completed": True,
                               "nextAction": "Exercise sheet 3", "color": "#5586CA", "desiredGrade": 5.5})
        self.assertEqual(response.status_code, 200)
        subject = self.plan()["subjects"][0]
        self.assertEqual((subject["targetHours"], subject["examDate"], subject["completed"], subject["nextAction"],
                          subject["color"], subject["desiredGrade"]),
                         (65.5, "2027-01-28", True, "Exercise sheet 3", "#5586CA", 5.5))
        for bad in ({"targetHours": -1}, {"targetHours": "5"}, {"examDate": "2027-02-30"}, {"completed": "yes"},
                    {"nextAction": "x" * 1001}, {"color": "blue"}, {"desiredGrade": 7}, {}):
            self.assertEqual(self.patch(bad).status_code, 400, bad)
        self.assertEqual(self.patch({"targetHours": 1}, course_id=2).status_code, 404)   # not added

    def test_record_and_clear_hours(self):
        self.add(1)
        self.add(2)
        self.assertEqual(self.hours("2027-01-05", 2.5).status_code, 200)
        self.assertEqual(self.plan()["subjects"][0]["hours"], {"2027-01-05": 2.5})
        self.assertEqual(self.hours("2027-01-05", 3).status_code, 200)            # replaces
        self.assertEqual(self.hours("2027-01-05", 22, course_id=2).status_code, 400)   # 3 + 22 > 24 h
        self.assertEqual(self.hours("2027-01-05", 21, course_id=2).status_code, 200)
        self.assertEqual(self.hours("2027-01-05", None).status_code, 200)         # clears
        self.assertEqual(self.plan()["subjects"][0]["hours"], {})
        self.assertEqual(self.hours("2026-11-01", 1).status_code, 400)            # outside the study phase
        self.assertEqual(self.hours("2027-01-06", 25).status_code, 400)

    def test_save_sessions(self):
        self.add(1)
        a = {"id": "a", "subjectId": "course-1", "date": "2027-01-05", "start": "09:00", "hours": 2}
        b = {"id": "b", "subjectId": "course-1", "date": "2027-01-05", "start": "11:00", "hours": 1.5}
        self.assertEqual(self.sessions([b, a]).status_code, 200)
        self.assertEqual([s["id"] for s in self.plan()["sessions"]], ["a", "b"])
        self.assertEqual(self.sessions([a]).status_code, 200)                       # replaces the list
        self.assertEqual([s["id"] for s in self.plan()["sessions"]], ["a"])
        overlapping = {**b, "start": "10:30"}
        self.assertEqual(self.sessions([a, overlapping]).json["error"], "Study sessions cannot overlap. Choose another time.")
        for bad in ({**a, "subjectId": "course-2"}, {**a, "date": "2026-11-01"}, {**a, "start": "9:00"},
                    {**a, "start": "23:00", "hours": 2}, {**a, "hours": 0}):
            self.assertEqual(self.sessions([bad]).status_code, 400, bad)
        self.assertEqual(self.sessions([a, a]).status_code, 400)                    # duplicate id
        self.assertEqual([s["id"] for s in self.plan()["sessions"]], ["a"])         # a failed save changes nothing

    def test_removing_a_course_removes_its_hours_and_sessions(self):
        self.add(1)
        self.hours("2027-01-05", 2)
        self.sessions([{"id": "a", "subjectId": "course-1", "date": "2027-01-05", "start": "09:00", "hours": 2}])
        self.client.delete("/api/semesters/2026W/courses/1", headers=ALICE)
        with self.app.app_context():
            conn = db.get_db()
            self.assertEqual(conn.execute("SELECT count(*) FROM study_hours").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM study_sessions").fetchone()[0], 0)
        self.add(1)
        self.assertEqual(self.plan()["subjects"][0]["hours"], {})

    def test_plans_are_per_user(self):
        self.add(1)
        self.hours("2027-01-05", 2)
        self.assertEqual(self.plan(user=BOB)["subjects"], [])
        self.assertEqual(self.patch({"targetHours": 1}, user=BOB).status_code, 404)
        self.assertEqual(self.hours("2027-01-05", 1, user=BOB).status_code, 404)
        self.assertEqual(self.sessions([{"id": "x", "subjectId": "course-1", "date": "2027-01-05", "start": "09:00",
                                         "hours": 1}], user=BOB).status_code, 400)


class SelectedSemesterTests(PlannerCase):
    def select(self, semkez, user=ALICE):
        return self.client.put("/api/semesters/selected", json={"semkez": semkez}, headers=user)

    def test_the_choice_is_stored_per_user(self):
        self.assertEqual(self.select("2027S").get_json(), {"selected": "2027S"})
        self.assertEqual(self.get("/api/semesters").get_json()["selected"], "2027S")
        self.assertEqual(self.get("/api/semesters", user=BOB).get_json()["selected"], "2026W")

    def test_only_offered_semesters_can_be_chosen(self):
        for bad in ("2019W", "nonsense", None):
            self.assertEqual(self.select(bad).status_code, 400, bad)
        self.assertEqual(self.get("/api/semesters").get_json()["selected"], "2026W")

    def test_an_old_semester_stays_reachable_after_the_catalogue_drops_it(self):
        self.add(2, "2027S")
        self.client.put("/api/semesters/2027S/courses/2/hours/2027-06-03", json={"hours": 2}, headers=ALICE)
        self.select("2027S")
        with self.app.app_context():   # the sync moves on: 2027S has no offerings anymore
            conn = db.get_db()
            with conn:
                conn.execute("DELETE FROM course_offerings WHERE semkez = '2027S'")
        body = self.get("/api/semesters").get_json()
        self.assertIn({"semkez": "2027S", "label": "FS27", "inCatalogue": False}, body["available"])
        self.assertEqual(body["selected"], "2027S")
        plan = self.get("/api/semesters/2027S/plan").get_json()
        self.assertEqual(plan["subjects"][0]["hours"], {"2027-06-03": 2})
        self.assertEqual(self.client.patch("/api/semesters/2027S/courses/2", json={"targetHours": 5}, headers=ALICE).status_code, 200)
        # Without the catalogue there is nothing to search or add.
        self.assertEqual(self.get("/api/courses?q=algebra&semkez=2027S").status_code, 400)
        self.assertEqual(self.add(2, "2027S").get_json()["error"],
                         "Courses can only be added to semesters in the course catalogue.")
        # Bob has no plan there, so for him it is simply unavailable.
        self.assertEqual(self.get("/api/semesters/2027S/plan", user=BOB).status_code, 400)

    def test_a_stored_choice_that_is_no_longer_offered_falls_back_to_current(self):
        self.select("2027S")
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute("DELETE FROM course_offerings WHERE semkez = '2027S'")
        self.assertEqual(self.get("/api/semesters").get_json()["selected"], "2026W")


class SchemaUpgradeTests(unittest.TestCase):
    def test_an_old_semester_courses_table_gets_the_plan_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            import sqlite3
            from pathlib import Path
            old = sqlite3.connect(Path(temp) / "app.db")
            old.executescript("""CREATE TABLE semester_courses (semester_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
                                 desired_grade REAL, PRIMARY KEY (semester_id, course_id));
                                 INSERT INTO semester_courses VALUES (1, 2, NULL);""")
            old.commit()
            old.close()
            app = build_app(temp)
            with app.app_context():
                row = db.get_db().execute("SELECT target_hours, completed, next_action, exam_date FROM semester_courses").fetchone()
            self.assertEqual(tuple(row), (0, 0, "", None))

    def test_an_old_users_table_gets_the_selected_semester(self):
        with tempfile.TemporaryDirectory() as temp:
            import sqlite3
            from pathlib import Path
            old = sqlite3.connect(Path(temp) / "app.db")
            old.executescript("""CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                                 display_name TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
                                 birth_date TEXT, study_start TEXT);
                                 INSERT INTO users (email) VALUES ('alice@ethz.ch');""")
            old.commit()
            old.close()
            app = build_app(temp)
            add_catalogue(app)
            with patch("planner.semester_of", return_value="2026W"):
                body = app.test_client().get("/api/semesters", headers=ALICE).get_json()
            self.assertEqual(body["selected"], "2026W")


if __name__ == "__main__":
    unittest.main()
