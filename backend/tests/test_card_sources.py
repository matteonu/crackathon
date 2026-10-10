"""Citations survive generation, persistence, review and source-file lifecycle changes."""
import unittest
import uuid

import db
from learning import pdf_study
from tests.support import build_app
from tests import test_scheduler as fixtures
from tests.test_scheduler import ALICE, BOB, CARD


class CardSources(unittest.TestCase):
    setUp = fixtures.PersistedScheduler.setUp
    material = fixtures.PersistedScheduler.material
    generated = fixtures.PersistedScheduler.generated
    session = fixtures.PersistedScheduler.session
    rate = fixtures.PersistedScheduler.rate

    def test_sources_survive_review_regeneration_rename_move_and_restart(self):
        pdf = self.material()
        question = {**CARD, 'source_pages': [3, 1, 3], 'evidence': 'The definition on page one and diagram on page three.'}
        deck = self.generated(pdf, [question])
        expected = {'pdfId': pdf['id'], 'pdfName': pdf['name'], 'pages': [1, 3], 'evidence': question['evidence']}
        first = self.session()['cards'][0]
        self.assertEqual(first['source'], expected)
        self.assertEqual(deck['outputs']['flashcards']['cards'][0]['source'], expected)
        self.assertEqual(self.rate(first, 'easy').status_code, 200)
        updated = self.generated(pdf, [{**question, 'evidence': 'More precise supporting evidence.'}])
        card = updated['outputs']['flashcards']['cards'][0]
        self.assertEqual(card['id'], first['id'])
        self.assertEqual(self.session()['cards'], [])  # Citation edits do not reset learning progress.
        folder = self.material('folder', 'Other chapter')
        self.client.patch('/api/materials/'+deck['id'], headers=ALICE, json={'parentId': folder['id']})
        self.client.patch('/api/materials/'+pdf['id'], headers=ALICE, json={'name': 'Renamed.pdf'})
        restarted = build_app(self.temp.name)
        self.addCleanup(restarted.extensions['learning_jobs'].pool.shutdown, wait=True)
        saved = restarted.test_client().get('/api/materials/'+deck['id'], headers=ALICE).get_json()
        source = saved['outputs']['flashcards']['cards'][0]['source']
        self.assertEqual(source, {**expected, 'pdfName': 'Renamed.pdf', 'evidence': 'More precise supporting evidence.'})
        self.assertEqual(saved['parentId'], folder['id'])
        self.client.delete('/api/materials/'+pdf['id'], headers=ALICE)
        saved = self.client.get('/api/materials/'+deck['id'], headers=ALICE).get_json()
        self.assertEqual(saved['outputs']['flashcards']['cards'][0]['source'], {**source, 'pdfId': None})
        # Surviving cards can still be edited and reviewed without a dangling PDF link.
        self.assertEqual(self.client.patch('/api/materials/'+deck['id'], headers=ALICE,
                        json={'outputs': saved['outputs']}).status_code, 200)
        with self.app.app_context():
            self.assertEqual(db.get_db().execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_source_validation_and_ownership_while_legacy_cards_still_work(self):
        pdf = self.material()
        deck = self.generated(pdf)
        self.assertNotIn('source', deck['outputs']['flashcards']['cards'][0])
        foreign = self.client.post('/api/materials', headers=BOB, json={
            'id': str(uuid.uuid4()), 'subjectId': 'subject', 'kind': 'pdf',
            'name': 'Private.pdf', 'category': 'Slides'}).get_json()
        source = {'pdfId': pdf['id'], 'pdfName': pdf['name'], 'pages': [1], 'evidence': 'Supporting passage.'}
        url = '/api/materials/'+deck['id']+'/cards'
        for invalid in [None, [], [0], [-1], [True], [1.5], ['1']]:
            response = self.client.post(url, headers=ALICE, json={'cards': [{**CARD, 'source': {**source, 'pages': invalid}}]})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(url, headers=ALICE, json={'cards': [{**CARD,
            'source': {**source, 'pdfId': foreign['id']}}]}).status_code, 400)
        self.assertEqual(self.client.post(url, headers=ALICE, json={'cards': [{**CARD,
            'source': {**source, 'evidence': ''}}]}).status_code, 400)
        self.assertEqual(self.client.get('/api/materials/'+deck['id'], headers=ALICE).get_json(), deck)

    def test_upgrade_adds_nullable_source_fields_without_changing_card_progress(self):
        deck = self.generated(self.material())
        first = self.session()['cards'][0]
        self.assertEqual(self.rate(first, 'easy').status_code, 200)
        with self.app.app_context():
            conn = db.get_db()
            before = tuple(conn.execute('SELECT * FROM flashcard_progress').fetchone())
            with conn:
                for column in ['source_pdf_id', 'source_pdf_name', 'source_pages', 'source_evidence']:
                    conn.execute('ALTER TABLE flashcards DROP COLUMN '+column)
        restarted = build_app(self.temp.name)
        self.addCleanup(restarted.extensions['learning_jobs'].pool.shutdown, wait=True)
        self.assertEqual(restarted.test_client().get('/api/materials/'+deck['id'], headers=ALICE).get_json(), deck)
        with restarted.app_context():
            self.assertEqual(tuple(db.get_db().execute('SELECT * FROM flashcard_progress').fetchone()), before)

    def test_model_output_rejects_missing_evidence_or_out_of_range_pages(self):
        card = {**CARD, 'category': pdf_study.CATEGORIES[0], 'source_pages': [2], 'evidence': 'Supported on page two.'}
        for updates in [{'source_pages': []}, {'source_pages': [0]}, {'source_pages': [4]}, {'source_pages': [True]}, {'evidence': ''}]:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                pdf_study.validate_cards({'cards': [{**card, **updates}]}, [card['category']], {1, 2, 3}, [], True)
        self.assertEqual(pdf_study.validate_cards({'cards': [card]}, [card['category']], {1, 2, 3}, [], True), [card])
