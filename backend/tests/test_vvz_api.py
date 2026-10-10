"""The /api/vvz endpoints, against a database built from the fake dump in test_vvz."""
import os
import tempfile
import unittest

from tests.support import build_app
from tests.test_vvz import make_dump
from vvz import sync

USER = {"X-User-Id": "alice@ethz.ch", "X-User-Name": "Alice"}


class VvzApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dump = os.path.join(self.tmp.name, "database.db")
        self.db = os.path.join(self.tmp.name, "vvz.db")
        make_dump(self.dump)

    def tearDown(self):
        self.tmp.cleanup()

    def test_503_before_the_first_sync(self):
        client = build_app(self.tmp.name, VVZ_DB_PATH=self.db).test_client()
        response = client.get("/api/vvz/status", headers=USER)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "VVZ data is not synced yet")

    def test_needs_a_user_like_every_api_route(self):
        client = build_app(self.tmp.name, VVZ_DB_PATH=self.db).test_client()
        self.assertEqual(client.get("/api/vvz/units").status_code, 401)

    def test_units_and_timetable(self):
        sync.build_db(self.dump, self.db, ["2025S", "2026W"])
        client = build_app(self.tmp.name, VVZ_DB_PATH=self.db).test_client()

        status = client.get("/api/vvz/status", headers=USER).get_json()
        self.assertEqual(status["semesters"], "2025S,2026W")

        hits = client.get("/api/vvz/units?q=analysis&semkez=2025S", headers=USER).get_json()
        self.assertEqual([h["number"] for h in hits], ["401-0212-16L"])

        unit = client.get("/api/vvz/units/188507", headers=USER).get_json()
        self.assertEqual(unit["credits"], 7.0)
        lecture = next(c for c in unit["courses"] if c["type"] == "V")
        self.assertEqual(lecture["timeslots"][0]["weekday_name"], "Mon")

        self.assertEqual(client.get("/api/vvz/units/1", headers=USER).status_code, 404)
        self.assertEqual(client.get("/api/vvz/timetable?ids=x", headers=USER).status_code, 400)
        self.assertEqual(client.get("/api/vvz/units?limit=x", headers=USER).status_code, 400)

        rows = client.get("/api/vvz/timetable?ids=188507,204074", headers=USER).get_json()
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["inherited_from"] for r in rows}, {None, "2025W"})


if __name__ == "__main__":
    unittest.main()
