"""The /api/courses endpoints and dump-seed, against a catalogue imported from the fake dump."""
import json
import os
import tempfile
import unittest

import db
from tests.support import build_app
from tests.test_vvz import make_dump
from vvz import sync

USER = {"X-User-Id": "alice@ethz.ch", "X-User-Name": "Alice"}


class CoursesApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dump = os.path.join(self.tmp.name, "database.db")
        make_dump(self.dump)
        self.app = build_app(self.tmp.name, seed=True)
        self.db = self.app.config["DATABASE_PATH"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_needs_a_user_like_every_api_route(self):
        self.assertEqual(self.app.test_client().get("/api/courses").status_code, 401)

    def test_seeded_courses_are_searchable_before_any_sync(self):
        client = self.app.test_client()
        self.assertEqual(client.get("/api/courses/sync-status", headers=USER).get_json(), {})
        hits = client.get("/api/courses?q=Analysis", headers=USER).get_json()
        self.assertEqual([(h["code"], h["ects"], h["offering_id"]) for h in hits], [("401-0212-16L", 8, None)])

    def test_sync_fills_the_seeded_catalogue_in_place(self):
        with self.app.app_context():
            before = {r["code"]: r["id"] for r in db.get_db().execute("SELECT id, code FROM courses")}
        sync.import_dump(self.dump, self.db, ["2025S", "2026W"])
        client = self.app.test_client()

        self.assertEqual(client.get("/api/courses/sync-status", headers=USER).get_json()["semesters"], "2025S,2026W")
        hits = client.get("/api/courses?q=analysis&semkez=2025S", headers=USER).get_json()
        self.assertEqual([(h["code"], h["ects"], h["id"]) for h in hits], [("401-0212-16L", 7, before["401-0212-16L"])])

        course = client.get(f"/api/courses/{before['401-0212-16L']}", headers=USER).get_json()
        self.assertEqual(course["offering"]["semkez"], "2025S")
        lecture = next(l for l in course["offering"]["lectures"] if l["type"] == "V")
        self.assertEqual(lecture["timeslots"][0]["weekday_name"], "Mon")
        self.assertEqual(client.get(f"/api/courses/{before['401-0212-16L']}?semkez=2026W", headers=USER).get_json()["offering"], None)

        # The dashboard still works and now shows VVZ's ECTS for the demo user's courses.
        dashboard = client.get("/api/dashboard", headers=USER).get_json()
        ects = {c["code"]: c["ects"] for s in dashboard["semesters"] for c in s["courses"]}
        self.assertEqual(ects.get("401-0212-16L"), 7)

        self.assertEqual(client.get("/api/courses/999999", headers=USER).status_code, 404)
        self.assertEqual(client.get("/api/courses/timetable?ids=x&semkez=2026W", headers=USER).status_code, 400)
        self.assertEqual(client.get("/api/courses/timetable?ids=1", headers=USER).status_code, 400)
        self.assertEqual(client.get("/api/courses?limit=x", headers=USER).status_code, 400)

        ids = f"{before['401-0212-16L']},{before['401-0131-00L']}"
        rows = client.get(f"/api/courses/timetable?ids={ids}&semkez=2026W", headers=USER).get_json()
        self.assertEqual([(r["code"], r["inherited_from"]) for r in rows], [("401-0131-00L", "2025W")])

    def test_dump_seed_leaves_the_synced_catalogue_out(self):
        sync.import_dump(self.dump, self.db, ["2025S", "2026W"])
        out_dir = os.path.join(self.tmp.name, "seed_out")
        self.app.config["SEED_DIRS"] = [out_dir]
        with self.app.app_context():
            written = db.dump_seed()
        names = {os.path.basename(p).split("_", 1)[1] for p in written}
        self.assertNotIn("course_offerings.json", names)
        self.assertNotIn("vvz_meta.json", names)
        with open(next(p for p in written if p.endswith("_courses.json"))) as f:
            codes = {row["code"] for row in json.load(f)}
        # Only the courses the demo data references, not every VVZ course.
        self.assertIn("401-0212-16L", codes)
        self.assertEqual(len(codes), 5)


if __name__ == "__main__":
    unittest.main()
