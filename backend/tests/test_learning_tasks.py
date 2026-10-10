"""Summary-only uploads and explicit, category-aware flashcard generation."""
import json
import argparse
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid

from learning import pdf_study
from learning.jobs import StudyJobs
from tests.support import build_app
from tests.test_learning import FIXTURE, fake_model


class LearningTaskTests(unittest.TestCase):
    def wait_result(self, jobs, document_id, mode, task):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = jobs.result(document_id, mode, task)
            # Wait until the worker releases the active slot as well as writing the result.
            with jobs.lock:
                active = (document_id, f'{task}:{mode}') in jobs.active
            if result['status'] in {'complete', 'error'} and not active:
                self.assertEqual(result['status'], 'complete', result)
                return result
            time.sleep(.02)
        self.fail('The test job did not finish')

    def test_summary_never_generates_cards_and_explicit_generation_reuses_it(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(pdf_study, 'API_KEY', 'test-only'), \
             patch.object(pdf_study, 'request_json', side_effect=fake_model) as request:
            jobs = StudyJobs(Path(temp), questions=5)
            document_id = str(uuid.uuid4())
            try:
                jobs.submit(document_id, 'slides.pdf', FIXTURE.read_bytes(), 'deep', task='summary')
                summary = self.wait_result(jobs, document_id, 'deep', 'summary')
                self.assertEqual(summary['requested_questions'], 0)
                self.assertEqual(summary['documents'][0]['questions'], [])
                self.assertEqual(summary['model'], pdf_study.SUMMARY_MODEL)
                self.assertEqual(summary['documents'][0]['model'], pdf_study.SUMMARY_MODEL)
                self.assertEqual(request.call_args.args[1], pdf_study.SUMMARY_MODEL)
                self.assertEqual([call.args[2]['stage'] for call in request.call_args_list], ['abstract'])
                self.assertFalse(jobs.result_path(document_id, 'shallow').exists())
                request.reset_mock()
                jobs.submit(document_id, 'slides.pdf', mode='shallow', questions=7)
                cards = self.wait_result(jobs, document_id, 'shallow', 'flashcards')
                self.assertEqual(len(cards['documents'][0]['questions']), 7)
                self.assertEqual(cards['model'], pdf_study.MODEL)
                self.assertEqual(cards['documents'][0]['model'], pdf_study.MODEL)
                self.assertTrue(all(call.args[1] == pdf_study.MODEL for call in request.call_args_list))
                self.assertEqual(cards['documents'][0]['abstract'], summary['documents'][0]['abstract'])
                self.assertEqual([call.args[2]['stage'] for call in request.call_args_list], ['preview', 'questions'])
                # A changed count starts a new run using the same stored PDF.
                jobs.submit(document_id, 'slides.pdf', mode='shallow', questions=8)
                changed = self.wait_result(jobs, document_id, 'shallow', 'flashcards')
                self.assertEqual(len(changed['documents'][0]['questions']), 8)
                self.assertEqual(jobs.result(document_id, 'deep', 'summary'), summary)
                self.assertEqual(json.loads(jobs.result_path(document_id, 'shallow').read_text())['requested_questions'], 8)
            finally:
                jobs.pool.shutdown(wait=True)

    def test_summary_provider_settings_do_not_leak_into_card_requests(self):
        provider = Mock()
        provider.responses.create.return_value = SimpleNamespace(
            status='completed', output=[], output_text='{"abstract":"A single sentence."}')
        with tempfile.TemporaryDirectory() as temp, patch.object(pdf_study, 'API_KEY', 'test-only'), \
             patch('openai.OpenAI') as factory:
            factory.return_value.__enter__.return_value = provider
            args = argparse.Namespace(pdfs=[str(FIXTURE)], output=str(Path(temp) / 'summary.json'),
                                      sentences=1, questions=0, language='English', model=pdf_study.SUMMARY_MODEL,
                                      timeout=10, allow_empty_pages=False, deep_mode=True,
                                      task='summary', reasoning_effort='none')
            pdf_study.run(args)
            request = provider.responses.create.call_args.kwargs
            self.assertEqual(request['model'], pdf_study.SUMMARY_MODEL)
            self.assertEqual(request['reasoning'], {'effort': 'none'})
            self.assertEqual(request['text']['format']['schema'], pdf_study.SUMMARY_SCHEMA)
            self.assertEqual(request['input'][0]['content'][0]['type'], 'input_file')
            result = json.loads(Path(args.output).read_text())['documents'][0]
            self.assertEqual((result['sentence_count'], result['questions']), (1, []))
            pdf_study.request_json(provider, pdf_study.MODEL, {}, pdf_study.SUMMARY_SCHEMA, 'Other request')
            self.assertNotIn('reasoning', provider.responses.create.call_args.kwargs)

    def test_api_accepts_upload_categories_but_restricts_card_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            app = build_app(temp, DEV_USER='alice@ethz.ch')
            client = app.test_client()
            jobs = app.extensions['learning_jobs']
            with patch.object(jobs, 'submit', return_value={'status': 'queued'}) as submit:
                for category in ('Slides', 'Solutions', 'Scripts', 'Exercises', 'Exams', 'Notes'):
                    document_id = str(uuid.uuid4())
                    created = client.post('/api/materials', json={'id': document_id, 'subjectId': 'subject',
                                          'kind': 'pdf', 'name': category + '.pdf', 'category': category})
                    self.assertEqual(created.status_code, 201, created.get_json())
                    url = f'/api/learning/documents/{document_id}'
                    self.assertEqual(client.post(url, headers={'X-Learning-Task': 'summary', 'X-Learning-Mode': 'deep'}).status_code, 202)
                    self.assertEqual(submit.call_args.args[-1], 'summary')
                    submit.reset_mock()
                    cards = client.post(url, headers={'X-Learning-Task': 'flashcards', 'X-Flashcard-Count': '12'})
                    allowed = category in {'Slides', 'Solutions', 'Scripts'}
                    self.assertEqual(cards.status_code, 202 if allowed else 400, category)
                    self.assertEqual(submit.called, allowed)
                self.assertEqual(client.post(url, headers={'X-Learning-Task': 'invalid'}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
