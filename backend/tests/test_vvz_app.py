"""The catalogue inside the app: reset-db refills it from the cache, dump-seed leaves it out."""
import json
import os
import tempfile
import unittest
import zipfile

import db
from tests.support import build_app
from tests.test_vvz import make_dump
from vvz import sync

USER = {"X-User-Id": "alice@ethz.ch", "X-User-Name": "Alice"}


class CatalogueInAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        dump = os.path.join(self.tmp.name, "database.db")
        make_dump(dump)
        # The cached download the sync would have left behind.
        zip_path, info_path = sync.cache_paths(self.tmp.name)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(dump, "database.db")
        with open(info_path, "w") as f:
            json.dump({"dump_last_modified_ms": "123", "dump_size_in_bytes": "1"}, f)
        self.app = build_app(self.tmp.name, seed=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_offline_sync_fills_the_seeded_catalogue_in_place(self):
        with self.app.app_context():
            before = {r["code"]: (r["id"], r["ects"]) for r in db.get_db().execute("SELECT id, code, ects FROM courses")}
        self.assertEqual(before["401-0212-16L"][1], 8)   # the demo seed's guess

        self.assertTrue(sync.sync(offline=True, semesters=["2025S", "2026W"], db_path=self.app.config["DATABASE_PATH"], data_dir=self.tmp.name))
        with self.app.app_context():
            after = {r["code"]: (r["id"], r["ects"]) for r in db.get_db().execute("SELECT id, code, ects FROM courses")}
        self.assertEqual(after["401-0212-16L"], (before["401-0212-16L"][0], 7))   # same id, VVZ's ECTS
        self.assertEqual(after["401-0131-00L"][0], before["401-0131-00L"][0])

        # The dashboard still joins the same rows and now shows VVZ's values.
        dashboard = self.app.test_client().get("/api/dashboard", headers=USER).get_json()
        ects = {c["code"]: c["ects"] for s in dashboard["semesters"] for c in s["courses"]}
        self.assertEqual(ects.get("401-0212-16L"), 7)

        # A second offline sync with the same dump and semesters is a no-op.
        self.assertFalse(sync.sync(offline=True, semesters=["2025S", "2026W"], db_path=self.app.config["DATABASE_PATH"], data_dir=self.tmp.name))

    def test_dump_seed_leaves_the_synced_catalogue_out(self):
        sync.sync(offline=True, semesters=["2025S", "2026W"], db_path=self.app.config["DATABASE_PATH"], data_dir=self.tmp.name)
        out_dir = os.path.join(self.tmp.name, "seed_out")
        self.app.config["SEED_DIRS"] = [out_dir]
        with self.app.app_context():
            written = db.dump_seed()
        names = {os.path.basename(p).split("_", 1)[1] for p in written}
        self.assertNotIn("course_offerings.json", names)
        self.assertNotIn("vvz_meta.json", names)
        with open(next(p for p in written if p.endswith("_courses.json"))) as f:
            codes = {row["code"] for row in json.load(f)}
        # Only the courses the demo data references (seed_demo/02_courses.json), not every VVZ course.
        self.assertIn("401-0212-16L", codes)
        with open(os.path.join(os.path.dirname(db.BACKEND_DIR), "backend", "seed_demo", "02_courses.json")) as f:
            demo_codes = {row["code"] for row in json.load(f)}
        self.assertTrue(codes <= demo_codes, codes - demo_codes)
        self.assertLess(len(codes), 50)


if __name__ == "__main__":
    unittest.main()
