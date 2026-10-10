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


class PlannerTests(unittest.TestCase):
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

    def test_semesters_lists_current_and_available(self):
        body = self.get("/api/semesters").get_json()
        self.assertEqual(body["current"], "2026W")
        self.assertEqual(body["available"], [{"semkez": "2026W", "label": "HS26"}, {"semkez": "2027S", "label": "FS27"}])
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


if __name__ == "__main__":
    unittest.main()
