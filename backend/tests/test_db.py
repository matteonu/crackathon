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
        return [r['email'] for r in db.get_db().execute('SELECT email FROM users ORDER BY id')]


class SeedTests(unittest.TestCase):
    def test_production_starts_with_an_empty_database(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, seed=True, SEED_DIRS=PRODUCTION_SEED)
            with app.app_context():
                conn = db.get_db()
                counts = {table: conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                          for table in ('users', 'courses', 'course_resources', 'semesters', 'materials')}
            self.assertEqual(counts, {'users': 0, 'courses': 0, 'course_resources': 0,
                                      'semesters': 0, 'materials': 0})

    def test_the_demo_overlay_fills_the_same_database(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, seed=True, SEED_DIRS=DEMO_SEED)
            with app.app_context():
                conn = db.get_db()
                self.assertGreater(conn.execute('SELECT count(*) FROM courses').fetchone()[0], 0)
                self.assertGreater(conn.execute('SELECT count(*) FROM semesters').fetchone()[0], 0)
                self.assertGreater(conn.execute('SELECT count(*) FROM course_resources').fetchone()[0], 0)
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
