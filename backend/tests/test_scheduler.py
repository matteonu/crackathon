"""Notebook scheduling contracts and persisted, user-scoped integration behavior."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

import db
import decks
from learning.scheduler import FlashcardScheduler
from learning import pdf_study
from tests.support import build_app
from errors import RequestError

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
ALICE = {'X-User-Id': 'alice@ethz.ch'}
BOB = {'X-User-Id': 'bob@ethz.ch'}
CARD = {'question': 'Question?', 'answer': 'Answer.'}


class SchedulerRules(unittest.TestCase):
    def scheduler(self):
        return FlashcardScheduler([CARD], now=NOW)

    def test_new_card_rating_delays(self):
        for rating, delay, status in [('again', timedelta(minutes=1), 'learning'),
                                      ('hard', timedelta(minutes=5.5), 'learning'),
                                      ('good', timedelta(minutes=10), 'learning'),
                                      ('easy', timedelta(days=4), 'review')]:
            with self.subTest(rating=rating):
                s = self.scheduler()
                self.assertEqual(s.review((0,), rating, now=NOW), NOW + delay)
                self.assertEqual(s.get_card((0,)).status, status)

    def test_learning_graduation_review_and_lapse(self):
        s = self.scheduler()
        at = s.review((0,), 'good', now=NOW)
        at = s.review((0,), 'good', now=at)
        c = s.get_card((0,))
        self.assertEqual((c.status, c.maturity), ('review', 1))
        at = s.review((0,), 'good', now=at)
        self.assertEqual(c.maturity, 2.5)
        previous = at
        at = s.review((0,), 'again', now=at)
        self.assertEqual(at, previous + timedelta(minutes=10))
        self.assertEqual((c.status, c.maturity, c.ease, c.lapses), ('relearning', 1.25, 2.3, 1))
        previous = at
        at = s.review((0,), 'hard', now=at)
        self.assertEqual(at, previous + timedelta(minutes=15))
        at = s.review((0,), 'good', now=at)
        self.assertEqual((c.status, c.maturity, c.n_mistakes), ('review', 1.25, 1))

    def test_intervals_ease_floor_and_cap(self):
        s = self.scheduler()
        s.review((0,), 'easy', now=NOW)
        c = s.get_card((0,))
        s.review((0,), 'hard', now=c.due)
        self.assertAlmostEqual(c.maturity, 4.8)
        self.assertAlmostEqual(c.ease, 2.35)
        s.review((0,), 'easy', now=c.due)
        self.assertAlmostEqual(c.maturity, 4.8 * 2.35 * 1.3)
        c.ease, c.maturity = 1.3, 36500
        s.review((0,), 'hard', now=c.due)
        self.assertEqual((c.ease, c.maturity), (1.3, 36500))

    def test_due_filter_unique_selection_and_per_call_new_cap(self):
        s = FlashcardScheduler([CARD] * 12, now=NOW)
        self.assertEqual(len(s.get_session(limit=20, new_card_limit=5, now=NOW)), 5)
        first = s.get_session(limit=20, new_card_limit=5, now=NOW)
        self.assertEqual(first, s.get_session(limit=20, new_card_limit=5, now=NOW))
        s.review(first[0], 'again', now=NOW)
        self.assertNotIn(first[0], s.get_session(now=NOW))
        self.assertIn(first[0], s.get_session(now=NOW+timedelta(minutes=1)))
        self.assertEqual(len(s.get_session(limit=20, new_card_limit=5, now=NOW)), 5)

    def test_recursive_weighting_at_course_and_chapter_levels(self):
        s = FlashcardScheduler({'A': {'heavy': [CARD]*30, 'light': [CARD]*30},
                                'B': {'one': [CARD]*30, 'two': [CARD]*30}},
                               {('A',): 2, ('A', 'heavy'): 3}, now=NOW)
        indices = s.get_session(limit=24, now=NOW)
        self.assertEqual(sum(i[0] == 'A' for i in indices), 16)
        a = [i for i in indices if i[0] == 'A']
        self.assertEqual(sum(i[1] == 'heavy' for i in a), 12)
        self.assertEqual(len(indices), len(set(indices)))

    def test_analytics_and_round_trip(self):
        s = FlashcardScheduler({'Folder': [CARD]}, now=NOW)
        s.review(('Folder', 0), 'again', now=NOW, response_seconds=8)
        s.review(('Folder', 0), 'easy', now=NOW+timedelta(minutes=1), response_seconds=4)
        root = s.analytics(now=NOW)[0]
        self.assertEqual((root['reviews'], root['mistakes'], root['success_rate'], root['average_response_seconds']), (2, 1, .5, 6))
        restored = FlashcardScheduler.from_state({'Folder': [CARD]}, json.loads(json.dumps(s.to_state())))
        self.assertEqual(restored.to_state(), s.to_state())


class PersistedScheduler(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = build_app(self.temp.name)
        self.client = self.app.test_client()

    def material(self, kind='pdf', name='lecture.pdf', parent=None):
        response = self.client.post('/api/materials', headers=ALICE, json={
            'id': str(uuid.uuid4()), 'subjectId': 'subject', 'kind': kind,
            'name': name, 'parentId': parent, 'category': 'Notes'})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def generated(self, pdf, questions=None, mode='shallow'):
        with self.app.app_context():
            decks.persist_result(db.get_db(), pdf['id'], {'status': 'complete', 'mode': mode,
                'documents': [{'abstract': 'Summary.', 'questions': questions or [CARD]}]})
        return next(m for m in self.client.get('/api/materials', headers=ALICE).get_json() if m['kind'] == 'deck' and m['sourcePdfId'] == pdf['id'])

    def session(self, **query):
        response = self.client.get('/api/practice/session', query_string={'subject': 'subject', **query}, headers=ALICE)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def rate(self, card, rating='good', headers=ALICE):
        return self.client.post('/api/practice/review', headers=headers, json={
            'deckId': card['deckId'], 'cardId': card['id'], 'version': card['version'],
            'rating': rating, 'responseSeconds': 8})

    def test_reviews_persist_are_private_and_reject_duplicates(self):
        pdf = self.material()
        deck = self.generated(pdf)
        first = self.session()['cards'][0]
        self.assertEqual(first['predictions']['good']['seconds'], 600)
        self.assertEqual(self.rate(first, headers=BOB).status_code, 404)
        response = self.rate(first)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.rate(first).status_code, 409)
        self.assertEqual(self.session()['cards'], [])
        restarted = build_app(self.temp.name)
        root = restarted.test_client().get('/api/practice/analytics', headers=ALICE).get_json()[0]
        self.assertEqual((root['reviews'], root['states']['learning'], root['average_response_seconds']), (1, 1, 8))
        with restarted.app_context():
            self.assertEqual(db.get_db().execute('SELECT count(*) FROM flashcard_reviews WHERE deck_id=?', (deck['id'],)).fetchone()[0], 1)

    def test_move_and_rename_preserve_progress_source_deletion_disconnects(self):
        pdf = self.material()
        deck = self.generated(pdf)
        card = self.session()['cards'][0]
        self.assertEqual(self.rate(card, 'easy').status_code, 200)
        folder = self.material('folder', 'Other folder')
        changed = self.client.patch('/api/materials/'+deck['id'], headers=ALICE,
                                    json={'parentId': folder['id'], 'name': 'Renamed deck'})
        self.assertEqual(changed.status_code, 200, changed.get_json())
        self.assertEqual(self.client.delete('/api/materials/'+pdf['id'], headers=ALICE).status_code, 200)
        listing = self.client.get('/api/materials', headers=ALICE).get_json()
        kept = next(m for m in listing if m['id'] == deck['id'])
        self.assertIsNone(kept['sourcePdfId'])
        self.assertEqual(kept['outputs']['flashcards']['cards'][0]['id'], card['id'])
        root = self.client.get('/api/practice/analytics', headers=ALICE).get_json()[0]
        self.assertEqual(root['reviews'], 1)
        self.client.delete('/api/materials/'+deck['id'], headers=ALICE)
        with self.app.app_context():
            self.assertEqual(db.get_db().execute('SELECT count(*) FROM flashcard_progress').fetchone()[0], 0)
            self.assertEqual(db.get_db().execute('SELECT count(*) FROM flashcard_reviews').fetchone()[0], 0)

    def test_regeneration_reorders_unchanged_cards_and_retains_manual_cards(self):
        pdf = self.material()
        second = {'question': 'Second?', 'answer': 'Two.'}
        deck = self.generated(pdf, [CARD, second])
        first = self.session()['cards'][0]
        self.assertEqual(self.rate(first, 'easy').status_code, 200)
        self.client.post('/api/materials/'+pdf['id']+'/cards', headers=ALICE,
                         json={'cards': [{'question': 'Manual?', 'answer': 'Mine.'}]})
        changed = self.generated(pdf, [second, CARD], mode='deep')
        cards = changed['outputs']['flashcards']['cards']
        self.assertEqual(changed['id'], deck['id'])
        self.assertEqual(changed['generationMode'], 'deep')
        self.assertEqual(cards[1]['id'], first['id'])
        self.assertEqual(cards[2]['question'], 'Manual?')
        self.assertNotIn(first['id'], [c['id'] for c in self.session()['cards']])

    def test_content_changes_reset_progress_and_invalidate_open_sessions(self):
        deck = self.generated(self.material())
        before = self.session()['cards'][0]
        cards = deck['outputs']['flashcards']['cards']
        cards[0]['answer'] = 'Changed.'
        response = self.client.patch('/api/materials/'+deck['id'], headers=ALICE,
                                    json={'outputs': {'flashcards': {'cards': cards}}})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.rate(before).status_code, 409)
        after = self.session()['cards'][0]
        self.assertEqual((after['id'], after['version']), (before['id'], before['version']+1))
        self.assertEqual(self.rate(after, 'easy').status_code, 200)
        cards[0]['question'] = 'Changed question?'
        self.client.patch('/api/materials/'+deck['id'], headers=ALICE,
                          json={'outputs': {'flashcards': {'cards': cards}}})
        root = self.client.get('/api/practice/analytics', headers=ALICE).get_json()[0]
        self.assertEqual((root['reviews'], root['states']['new']), (0, 1))

    def test_folder_scope_and_weights(self):
        a = self.material('folder', 'A')
        b = self.material('folder', 'B')
        self.generated(self.material(name='a.pdf', parent=a['id']), [CARD]*12)
        self.generated(self.material(name='b.pdf', parent=b['id']), [CARD]*12)
        response = self.client.patch('/api/materials/'+a['id'], headers=ALICE, json={'folderWeight': 3})
        self.assertEqual(response.status_code, 200)
        cards = self.session(limit=8, newCardLimit=8)['cards']
        self.assertEqual(sum(c['fileName'] == 'a cards' for c in cards), 6)
        self.assertEqual(len(self.session(folder=a['id'], limit=20, newCardLimit=20)['cards']), 12)
        self.assertEqual(self.client.patch('/api/materials/'+a['id'], headers=ALICE, json={'folderWeight': 0}).status_code, 400)
        self.assertEqual(self.client.get('/api/practice/session?folder='+a['id'], headers=BOB).status_code, 404)
        stats = self.client.get('/api/practice/analytics?folder='+a['id'], headers=ALICE).get_json()
        self.assertEqual(stats[0]['priority'], 3)

    def test_limits_and_invalid_ratings_do_not_mutate_progress(self):
        self.generated(self.material(), [CARD]*8)
        self.assertEqual(len(self.session()['cards']), 5)
        self.assertEqual(len(self.session()['cards']), 5)
        card = self.session()['cards'][0]
        self.assertEqual(self.rate(card, True).status_code, 400)
        self.assertEqual(self.rate(card, 'invalid').status_code, 400)
        self.assertEqual(self.client.get('/api/practice/session?limit=-1', headers=ALICE).status_code, 400)
        self.assertEqual(self.session(newCardLimit=0)['cards'], [])
        self.assertEqual(self.session()['cards'][0]['version'], 0)
        self.assertEqual(self.client.post('/api/practice/review', headers=ALICE, json=[1]).status_code, 400)

    def test_background_generation_saves_deck_without_browser_polling(self):
        pdf = self.material()
        jobs = self.app.extensions['learning_jobs']
        fixture = Path(__file__).resolve().parents[2] / 'frontend/tests/fixtures/study-demo.pdf'
        def runner(args):
            result = jobs.read(Path(args.output))
            result['documents'] = [{'abstract': 'Generated summary.', 'questions': [CARD]*5,
                                    'complete': True, 'sentence_count': 1}]
            pdf_study.write_json(Path(args.output), result)
        jobs.runner = runner
        with patch.object(pdf_study, 'API_KEY', 'test-only'):
            jobs.submit(pdf['id'], pdf['name'], fixture.read_bytes(), questions=5)
            jobs.pool.shutdown(wait=True)
        self.assertEqual(jobs.result(pdf['id'])['status'], 'complete')
        listing = self.client.get('/api/materials', headers=ALICE).get_json()
        deck = next(m for m in listing if m['sourcePdfId'] == pdf['id'])
        self.assertEqual(len(deck['outputs']['flashcards']['cards']), 5)
        self.assertEqual(len(self.session()['cards']), 5)

    def test_invalid_card_update_rolls_back_progress_reset(self):
        deck = self.generated(self.material(), [CARD, {'question':'Two?', 'answer':'Two.'}])
        card = self.session()['cards'][0]
        self.assertEqual(self.rate(card, 'easy').status_code, 200)
        cards = deck['outputs']['flashcards']['cards']
        cards[0]['answer'] = 'Would reset this card.'
        # Another deck owns this ID, so replacement must roll back every earlier write.
        other = self.generated(self.material(name='other.pdf'))
        cards[1]['id'] = other['outputs']['flashcards']['cards'][0]['id']
        response = self.client.patch('/api/materials/'+deck['id'], headers=ALICE,
                                    json={'outputs': {'flashcards': {'cards': cards}}})
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            row = db.get_db().execute('SELECT * FROM flashcard_progress WHERE card_id=?', (card['id'],)).fetchone()
            self.assertEqual((row['n_times_seen'], row['status'], row['version']), (1, 'review', 1))


class LegacyMigration(unittest.TestCase):
    def test_failed_migration_leaves_original_schema_and_content_intact(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp)/'app.db')
            conn = sqlite3.connect(path)
            conn.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT);
                INSERT INTO users VALUES(1,'alice@ethz.ch');
                CREATE TABLE materials(id TEXT PRIMARY KEY,user_id INTEGER,subject_id TEXT,
                  parent_id TEXT,kind TEXT,name TEXT,category TEXT,marker TEXT,size INTEGER DEFAULT 0,
                  added_at INTEGER,outputs TEXT,processing TEXT);''')
            original = json.dumps({'flashcards': {'cards': [{'question': 123, 'answer': 'Malformed legacy card'}]}})
            conn.execute("INSERT INTO materials(id,user_id,subject_id,kind,name,category,marker,added_at,outputs) VALUES(?,1,'subject','pdf','bad.pdf','Notes','To read',0,?)",
                         (str(uuid.uuid4()), original))
            conn.commit()
            conn.close()
            with self.assertRaises(RequestError):
                build_app(temp)
            conn = sqlite3.connect(path)
            try:
                self.assertNotIn('source_pdf_id', [r[1] for r in conn.execute('PRAGMA table_info(materials)')])
                self.assertEqual(conn.execute('SELECT outputs FROM materials').fetchone()[0], original)
                self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='flashcards'").fetchone())
            finally:
                conn.close()

    def test_nested_legacy_materials_migrate_atomically_and_once(self):
        with tempfile.TemporaryDirectory() as temp:
            conn = sqlite3.connect(str(Path(temp)/'app.db'))
            schema = Path(db.SCHEMA_PATH).read_text().split('-- A deck is independent')[0]
            schema = schema.replace(", 'deck'", '').replace(
                '    source_pdf_id TEXT REFERENCES materials(id) ON DELETE SET NULL,\n', '').replace(
                "    generation_mode TEXT CHECK (generation_mode IN ('shallow', 'deep')),\n", '').replace(
                '    folder_weight REAL NOT NULL DEFAULT 1 CHECK (folder_weight > 0),\n', '').replace(
                '    processing TEXT,\n    UNIQUE (id, user_id)', '    processing TEXT')
            conn.executescript(schema)
            conn.execute("INSERT INTO users(id,email) VALUES(1,'alice@ethz.ch')")
            folder, pdf = str(uuid.uuid4()), str(uuid.uuid4())
            for id_, parent, kind, name, outputs in [(folder, None, 'folder', 'Folder', None),
                    (pdf, folder, 'pdf', 'lecture.pdf', json.dumps({'summary': {'text': 'Summary.'},
                          'flashcards': {'cards': [CARD, {**CARD, 'demo': False}]}}))]:
                conn.execute('''INSERT INTO materials(id,user_id,subject_id,parent_id,kind,name,category,
                                marker,added_at,outputs) VALUES(?,1,'subject',?,?,?,'Notes','To read',0,?)''',
                             (id_, parent, kind, name, outputs))
            conn.commit()
            conn.close()
            app = build_app(temp)
            listing = app.test_client().get('/api/materials', headers=ALICE).get_json()
            deck = next(m for m in listing if m['kind'] == 'deck')
            self.assertEqual((deck['sourcePdfId'], deck['parentId']), (pdf, folder))
            self.assertEqual(len(deck['outputs']['flashcards']['cards']), 2)
            source = next(m for m in listing if m['id'] == pdf)
            self.assertEqual(source['outputs'], {'summary': {'text': 'Summary.'}})
            again = build_app(temp).test_client().get('/api/materials', headers=ALICE).get_json()
            self.assertEqual(listing, again)
            with app.app_context():
                self.assertEqual(db.get_db().execute('PRAGMA foreign_key_check').fetchall(), [])
