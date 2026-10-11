"""The database lifecycle: what a restart keeps, and which seed a mode loads."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import BACKEND_DIR
import db
from material_types import CATEGORY_TYPES
from tests.support import build_app

PRODUCTION_SEED = [os.path.join(BACKEND_DIR, 'seed')]
DEMO_SEED = PRODUCTION_SEED + [os.path.join(BACKEND_DIR, 'seed_demo')]


def emails(app):
    with app.app_context():
        return [r['email'] for r in db.get_db().execute('SELECT email FROM users ORDER BY id')]


class SeedTests(unittest.TestCase):
    def test_document_type_migration_preserves_the_old_library_and_pdf(self):
        with tempfile.TemporaryDirectory() as temp:
            # Build the pre-migration table with its original material defaults.
            # Startup now rebuilds it for decks as well as adding document types.
            path = Path(temp) / 'app.db'
            conn = sqlite3.connect(path)
            try:
                conn.executescript('''CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, display_name TEXT);
                    INSERT INTO users VALUES (1, 'alice@ethz.ch', 'Alice');
                    CREATE TABLE materials (
                      id TEXT PRIMARY KEY, user_id INTEGER, subject_id TEXT, parent_id TEXT,
                      kind TEXT, name TEXT, description TEXT NOT NULL DEFAULT '', category TEXT,
                      marker TEXT NOT NULL DEFAULT 'To read', size INTEGER NOT NULL DEFAULT 0,
                      content TEXT, sha256 TEXT, added_at INTEGER NOT NULL DEFAULT 0, outputs TEXT, processing TEXT);''')
                for category in (*CATEGORY_TYPES, 'Notes', 'Books', 'Transcripts'):
                    conn.execute("INSERT INTO materials VALUES (?,1,'subject',NULL,'pdf',?,'Keep me',?,'Done',123,NULL,'digest',42,?,NULL)",
                                 (category, category + '.pdf', category, '{"summary":{"text":"Keep this."}}'))
                conn.execute("INSERT INTO materials (id, user_id, subject_id, kind, name, category) VALUES ('folder',1,'subject','folder','Folder','Slides')")
                conn.commit()
                original = conn.execute('SELECT * FROM materials ORDER BY id').fetchall()
                original_columns = [row[1] for row in conn.execute('PRAGMA table_info(materials)')]
            finally:
                conn.close()
            pdf = Path(temp) / 'learning' / 'Slides' / 'source.pdf'
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b'%PDF-existing-file')
            for _ in range(2):
                app = build_app(temp)
                self.addCleanup(app.extensions['learning_jobs'].pool.shutdown, wait=True)
                with app.app_context():
                    conn = db.get_db()
                    rows = conn.execute('SELECT * FROM materials ORDER BY id').fetchall()
                    self.assertEqual([tuple(row[column] for column in original_columns) for row in rows], original)
                    for row in rows:
                        expected = CATEGORY_TYPES.get(row['category']) if row['kind'] != 'folder' else None
                        self.assertEqual(row['type'], expected)
                    for invalid in ('unknown', 'cards'):
                        # Unknown codes and typed folders are rejected in SQL too.
                        with self.assertRaises(sqlite3.IntegrityError):
                            with conn:
                                conn.execute("UPDATE materials SET type = ? WHERE id = 'folder'", (invalid,))
                self.assertEqual(pdf.read_bytes(), b'%PDF-existing-file')

    def test_first_start_seeds_and_releases_the_database_file(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, SEED_IF_NEW=True, SEED_DIRS=DEMO_SEED)
            self.assertEqual(emails(app), ['alice@ethz.ch', 'bob@ethz.ch'])
            # Windows refuses to rename the file if a connection is still open.
            path = app.config['DATABASE_PATH']
            os.rename(path, path + '.moved')
            os.rename(path + '.moved', path)

    def test_reset_replaces_the_current_context_connection(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, seed=True, SEED_DIRS=DEMO_SEED)
            with app.app_context():
                db.upsert_user('guest@ethz.ch', 'Guest')
                db.reset_db()
                self.assertIsNone(db.get_user_by_email('guest@ethz.ch'))
                self.assertIsNotNone(db.get_user_by_email('alice@ethz.ch'))

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
                material = conn.execute("SELECT * FROM materials WHERE id=?",
                    ('6a3e1d60-d094-4a42-b549-5479229363fb',)).fetchone()
                self.assertEqual((material['subject_id'], material['category'], material['type']),
                                 ('course-9', 'Slides', 'slides'))
            source = Path(temp) / 'learning' / material['id'] / 'source.pdf'
            self.assertEqual(source.stat().st_size, material['size'])
            response = app.test_client().get(f"/api/materials/{material['id']}/file",
                                             headers={'X-User-Id': 'alice@ethz.ch'})
            self.assertEqual((response.status_code, len(response.data)), (200, material['size']))
            response.close()
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


class DatabaseConcurrencyTests(unittest.TestCase):
    def test_writer_can_commit_while_reader_keeps_its_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp)
            self.addCleanup(app.extensions['learning_jobs'].pool.shutdown, wait=True)
            self.addCleanup(app.extensions['mcq_jobs'].pool.shutdown, wait=True)
            path = app.config['DATABASE_PATH']
            reader, writer = db.connect(path), db.connect(path)
            try:
                reader.execute('BEGIN')
                self.assertEqual(reader.execute('SELECT COUNT(*) FROM users').fetchone()[0], 0)
                writer.execute('PRAGMA busy_timeout = 0')
                with writer:
                    writer.execute("INSERT INTO users(email) VALUES ('concurrent@ethz.ch')")
                # A catalogue write must not wait for an open reader to finish.
                self.assertEqual(reader.execute('SELECT COUNT(*) FROM users').fetchone()[0], 0)
                reader.rollback()
                self.assertEqual(reader.execute('SELECT COUNT(*) FROM users').fetchone()[0], 1)
            finally:
                reader.close()
                writer.close()

    def test_reloader_parent_does_not_start_background_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('app.vvz.sync.start_background') as sync, patch('app.DocumentChat.start') as chat:
                app = build_app(temp, START_BACKGROUND_TASKS=False,
                                VVZ_AUTO_SYNC=True, CHAT_BACKGROUND_TASKS=True)
                self.addCleanup(app.extensions['learning_jobs'].pool.shutdown, wait=True)
                self.addCleanup(app.extensions['mcq_jobs'].pool.shutdown, wait=True)
                sync.assert_not_called()
                chat.assert_not_called()
                self.assertFalse(app.extensions['document_chat'].background)


if __name__ == '__main__':
    unittest.main()
