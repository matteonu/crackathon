"""The database lifecycle: what a restart keeps, and which seed a mode loads."""
import os
import tempfile
import unittest

from app import BACKEND_DIR
import db
from tests.support import build_app

PRODUCTION_SEED = [os.path.join(BACKEND_DIR, 'seed')]
DEMO_SEED = PRODUCTION_SEED + [os.path.join(BACKEND_DIR, 'seed_demo')]


def emails(app):
    with app.app_context():
        return [r['email'] for r in db.connect().execute('SELECT email FROM users ORDER BY id')]


class SeedTests(unittest.TestCase):
    def test_the_production_seed_has_the_catalog_but_no_users(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, seed=True, SEED_DIRS=PRODUCTION_SEED)
            with app.app_context():
                courses = db.connect().execute('SELECT count(*) FROM courses').fetchone()[0]
            self.assertGreater(courses, 0)
            self.assertEqual(emails(app), [])

    def test_the_demo_overlay_adds_users_to_the_same_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, seed=True, SEED_DIRS=DEMO_SEED)
            with app.app_context():
                conn = db.connect()
                self.assertGreater(conn.execute('SELECT count(*) FROM courses').fetchone()[0], 0)
                self.assertGreater(conn.execute('SELECT count(*) FROM semesters').fetchone()[0], 0)
            self.assertEqual(emails(app), ['alice@ethz.ch', 'bob@ethz.ch'])

    def test_a_restart_keeps_the_data_and_still_applies_the_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, seed=True, SEED_DIRS=DEMO_SEED)
            app.test_client().get('/api/me', headers={'X-User-Id': 'guest@ethz.ch'})
            # A second app over the same file is what a redeploy does.
            restarted = build_app(temp, SEED_DIRS=DEMO_SEED)
            self.assertIn('guest@ethz.ch', emails(restarted))

    def test_reset_on_start_discards_what_users_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, seed=True, SEED_DIRS=DEMO_SEED)
            app.test_client().get('/api/me', headers={'X-User-Id': 'guest@ethz.ch'})
            fresh = build_app(temp, SEED_DIRS=DEMO_SEED, RESET_DB_ON_START=True)
            self.assertEqual(emails(fresh), ['alice@ethz.ch', 'bob@ethz.ch'])


if __name__ == '__main__':
    unittest.main()
