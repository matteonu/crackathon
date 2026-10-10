import argparse
import contextlib
import io
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

from learning import pdf_study
from learning.jobs import RequestError, StudyJobs
from tests.support import build_app

FIXTURE = Path(__file__).resolve().parents[2] / 'frontend/tests/fixtures/study-demo.pdf'


def fake_model(client, model, data, schema, label, file_input=None):
    """Deterministic API-boundary fixture; the production server never imports this."""
    if data['stage'] in {'abstract', 'revise_length', 'section_notes'}:
        return {'abstract': 'The document explains retrieval practice.'}
    cards = []
    for category, count in data['category_counts'].items():
        for index in range(count):
            cards.append({'category': category, 'question': f'{category}: review question {index + 1}?',
                          'answer': 'A test answer grounded in the synthetic fixture.',
                          'source_pages': [data['valid_source_pages'][0]], 'evidence': 'Synthetic fixture evidence.'})
    result = {'cards': cards}
    if data['stage'] == 'preview_and_abstract':
        result['abstract'] = 'The document explains retrieval practice.'
    return result


class PipelineTests(unittest.TestCase):
    def test_result_polling_retries_a_windows_sharing_violation(self):
        with tempfile.TemporaryDirectory() as temp:
            result = Path(temp) / 'result.json'
            result.write_text('{"status":"complete","documents":[]}', encoding='utf-8')
            original = Path.read_text
            attempts = []

            def temporary_lock(path, *args, **kwargs):
                attempts.append(path)
                if len(attempts) == 1:
                    raise PermissionError('A worker is replacing the result file')
                return original(path, *args, **kwargs)

            with patch.object(Path, 'read_text', autospec=True, side_effect=temporary_lock):
                self.assertEqual(StudyJobs.read(result)['status'], 'complete')
            self.assertEqual(len(attempts), 2)

    def test_json_write_retries_a_windows_sharing_violation(self):
        original = Path.replace
        attempts = []
        def temporary_lock(path, target):
            attempts.append(target)
            if len(attempts) == 1:
                raise PermissionError('File is being read by a poll request')
            return original(path, target)
        with tempfile.TemporaryDirectory() as temp, patch.object(Path, 'replace', autospec=True, side_effect=temporary_lock):
            output = Path(temp) / 'result.json'
            pdf_study.write_json(output, {'status': 'complete'})
            self.assertEqual(json.loads(output.read_text()), {'status': 'complete'})
            self.assertEqual(len(attempts), 2)

    def test_failed_generation_resumes_without_repeating_the_summary(self):
        stages = []
        def interrupt_once(client, model, data, schema, label, file_input=None):
            stages.append(data['stage'])
            if data['stage'] == 'questions' and stages.count('questions') == 1:
                raise pdf_study.WorkflowError('Temporary API failure')
            return fake_model(client, model, data, schema, label, file_input)
        with tempfile.TemporaryDirectory() as temp, patch.object(pdf_study, 'API_KEY', 'test-only'), \
             patch.object(pdf_study, 'DEEP_MODE', False), patch.object(pdf_study, 'request_json', side_effect=interrupt_once), \
             contextlib.redirect_stdout(io.StringIO()):
            output = Path(temp) / 'result.json'
            args = argparse.Namespace(pdfs=[str(FIXTURE)], output=str(output), sentences=1, questions=5,
                                      language='English', model='test-model', timeout=10, allow_empty_pages=False, feedback='')
            with self.assertRaises(pdf_study.WorkflowError):
                pdf_study.run(args)
            partial = json.loads(output.read_text())['documents'][0]
            self.assertEqual(partial['sentence_count'], 1)
            self.assertFalse(partial['complete'])
            # Checkpoints from before per-file card counts used a key without the count.
            state_path = next(output.with_suffix('.work').glob('*.json'))
            legacy_key = hashlib.sha256((str(FIXTURE.resolve()) + 'False').encode('utf-8')).hexdigest()[:24]
            state_path.rename(state_path.with_name(legacy_key + '.json'))
            pdf_study.run(args)
            self.assertTrue(json.loads(output.read_text())['documents'][0]['complete'])
            self.assertEqual(stages.count('preview_and_abstract'), 1)
            self.assertEqual(stages.count('preview'), 0)
            self.assertEqual(stages.count('questions'), 2)

    def test_sentence_counts_and_correction(self):
        self.assertEqual(pdf_study.count_sentences('A value of 3.14 is used.'), 1)
        self.assertEqual(pdf_study.count_sentences('Dr. Smith explains it. A second sentence follows.'), 2)
        self.assertEqual(pdf_study.count_sentences('第一句。第二句。'), 2)
        with patch.object(pdf_study, 'api_request', return_value='One corrected sentence.') as request:
            result = pdf_study.adjust_sentence_count(None, 'One. Two.', 1, 'English', 'model')
        self.assertEqual(result, 'One corrected sentence.')
        self.assertEqual(request.call_args.args[2]['requested_sentences'], 1)
        with patch.object(pdf_study, 'api_request', return_value='Still two. Sentences.'):
            with self.assertRaises(pdf_study.WorkflowError):
                pdf_study.adjust_sentence_count(None, 'One. Two.', 1, 'English', 'model')

    def test_real_pdf_pipeline_json_and_completed_resume(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(pdf_study, 'API_KEY', 'test-only'), \
             patch.object(pdf_study, 'DEEP_MODE', False), patch.object(pdf_study, 'request_json', side_effect=fake_model) as request, \
             contextlib.redirect_stdout(io.StringIO()):
            output = Path(temp) / 'result.json'
            args = argparse.Namespace(pdfs=[str(FIXTURE)], output=str(output), sentences=1, questions=5,
                                      language='English', model='test-model', timeout=10, allow_empty_pages=False, feedback='')
            pdf_study.run(args)
            record = json.loads(output.read_text())['documents'][0]
            self.assertTrue(record['complete'])
            self.assertEqual(record['sentence_count'], 1)
            self.assertEqual(record['requested_sentences'], 1)
            self.assertNotIn('requested_words', record)
            self.assertEqual(len(record['questions']), 5)
            for card in record['questions']:
                self.assertEqual(card['source_pdf'], FIXTURE.name)
                self.assertEqual(card['source_pages'], [1])
                self.assertTrue(card['evidence'])
            self.assertNotIn('test-only', output.read_text())
            for call in request.call_args_list:
                self.assertEqual(call.args[2]['requested_sentences'], 1)
                self.assertNotIn('requested_words', call.args[2])
            count = request.call_count
            pdf_study.run(args)
            self.assertEqual(request.call_count, count)
            # Old final JSON discarded references, but its validated checkpoint has them.
            saved = json.loads(output.read_text())
            saved['documents'][0]['questions'] = [{k: c[k] for k in ('question', 'answer')} for c in record['questions']]
            pdf_study.write_json(output, saved)
            pdf_study.run(args)
            self.assertEqual(request.call_count, count)
            self.assertEqual(json.loads(output.read_text())['documents'][0]['questions'], record['questions'])

    def test_upload_http_results_and_idempotency(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(pdf_study, 'API_KEY', 'test-only'), \
             patch.object(pdf_study, 'DEEP_MODE', False), patch.object(pdf_study, 'request_json', side_effect=fake_model), \
             contextlib.redirect_stdout(io.StringIO()):
            failures = []
            def tracked_runner(args):
                try:
                    return pdf_study.run(args)
                except Exception as exc:
                    failures.append(repr(exc))
                    raise
            jobs = StudyJobs(Path(temp) / 'learning', questions=5, runner=tracked_runner)
            app = build_app(temp, DEV_USER='alice@ethz.ch')
            app.extensions['learning_jobs'] = jobs
            client = app.test_client()
            document_id = str(uuid.uuid4())
            url = f'/api/learning/documents/{document_id}'
            pdf = FIXTURE.read_bytes()
            # The pipeline only works on a document the caller owns.
            self.assertEqual(client.post('/api/materials', json={
                'id': document_id, 'subjectId': 'subject', 'kind': 'pdf',
                'name': 'lecture.pdf', 'category': 'Slides'}).status_code, 201)
            self.assertEqual(client.post(f'/api/learning/documents/{uuid.uuid4()}', data=pdf,
                                         content_type='application/pdf').status_code, 404)
            def upload(data=pdf, **headers):
                return client.post(url, data=data, content_type='application/pdf',
                                   headers={'X-Filename': 'lecture.pdf', 'X-Flashcard-Count': '7', **headers})
            try:
                self.assertEqual(upload().status_code, 202)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    data = client.get(url + '/result.json').get_json()
                    if data['status'] in {'complete', 'error'}:
                        break
                    time.sleep(0.02)
                self.assertEqual(data['status'], 'complete', (data, failures))
                self.assertEqual(len(data['documents'][0]['questions']), 7)
                self.assertEqual(data['requested_questions'], 7)
                self.assertEqual(data, json.loads(jobs.result_path(document_id, 'shallow').read_text()))
                self.assertEqual(data['mode'], 'shallow')
                self.assertEqual(upload().get_json()['status'], 'complete')
                self.assertEqual(upload(data=b'not a pdf').status_code, 400)
                self.assertEqual(upload(**{'X-Learning-Mode': 'invalid'}).status_code, 400)
                self.assertEqual(client.get(url + '/result.json?mode=deep').status_code, 404)
                self.assertEqual(client.post(url, data=pdf, content_type='text/plain').status_code, 415)
                # A malformed id matches no route, so Flask answers the POST with 405.
                self.assertEqual(client.post('/api/learning/documents/not-a-uuid', data=pdf,
                                             content_type='application/pdf').status_code, 405)
                unknown = client.get('/api/learning/nothing-here')
                self.assertEqual((unknown.status_code, unknown.get_json()['error']), (404, 'Unknown endpoint.'))
                for count in ('0', '4', '301', '5.5', 'abc'):
                    self.assertEqual(upload(**{'X-Flashcard-Count': count}).status_code, 400, count)
                with self.assertRaises(RequestError) as conflict:
                    jobs.submit(document_id, 'other.pdf', b'%PDF-different file')
                self.assertEqual(conflict.exception.status, 409)
                response = client.delete(url)
                self.assertTrue(response.get_json()['deleted'])
                self.assertFalse((Path(temp) / 'learning' / document_id).exists())
                self.assertEqual(client.get(url + '/result.json').status_code, 404)
                self.assertEqual(client.delete(url).status_code, 200)
                self.assertEqual(upload().status_code, 410)
            finally:
                jobs.pool.shutdown(wait=True)

    def test_concurrent_modes_use_separate_inputs_results_and_checkpoints(self):
        barrier = threading.Barrier(2)
        calls = []
        def inspect_request(client, model, data, schema, label, file_input=None):
            deep = file_input is not None
            calls.append((deep, data['stage']))
            if deep:
                self.assertEqual(file_input['type'], 'input_file')
                self.assertTrue(file_input['file_data'].startswith('data:application/pdf;base64,'))
                self.assertEqual(data['source_pages'], [])
            else:
                self.assertTrue(data['source_pages'])
            if data['stage'] == 'preview_and_abstract':
                barrier.wait(timeout=10)
            return fake_model(client, model, data, schema, label, file_input)
        with tempfile.TemporaryDirectory() as temp, patch.object(pdf_study, 'API_KEY', 'test-only'), \
             patch.object(pdf_study, 'DEEP_MODE', True), patch.object(pdf_study, 'request_json', side_effect=inspect_request), \
             contextlib.redirect_stdout(io.StringIO()):
            jobs = StudyJobs(Path(temp), questions=5)
            document_id = str(uuid.uuid4())
            try:
                for mode in ('shallow', 'deep'):
                    jobs.submit(document_id, 'lecture.pdf', FIXTURE.read_bytes(), mode)
                jobs.pool.shutdown(wait=True)
                for mode in ('shallow', 'deep'):
                    data = jobs.result(document_id, mode)
                    self.assertEqual(data['status'], 'complete', data)
                    self.assertEqual(data['mode'], mode)
                    self.assertEqual(data['documents'][0]['deep_mode'], mode == 'deep')
                    self.assertEqual(data['documents'][0]['sentence_count'], 1)
                    self.assertEqual(len(data['documents'][0]['questions']), 5)
                    for card in data['documents'][0]['questions']:
                        self.assertEqual(card['source_pdf'], 'lecture.pdf')
                        self.assertEqual(card['source_pdf_id'], document_id)
                        self.assertEqual(card['source_pages'], [1])
                        self.assertTrue(card['evidence'])
                    self.assertTrue(list((Path(temp) / document_id / mode / 'result.work').glob('*.json')))
                    self.assertEqual(jobs.submit(document_id, 'lecture.pdf', FIXTURE.read_bytes(), mode), data)
                self.assertEqual(len(calls), 4)
                self.assertEqual(sum(deep for deep, _ in calls), 2)
            finally:
                jobs.pool.shutdown(wait=True)

    def test_deep_mode_accepts_pages_without_extractable_text(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'no-text.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.write(path)
            with self.assertRaises(pdf_study.WorkflowError):
                pdf_study.prepare_source(path, False, False)
            source = pdf_study.prepare_source(path, False, True)
            self.assertEqual(source['valid_pages'], {1})
            self.assertIsNotNone(source['file_input'])

    def test_deleting_an_active_pdf_stops_next_requests_and_removes_every_mode(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []
        def waiting_model(client, model, data, schema, label, file_input=None):
            calls.append(data['stage'])
            entered.set()
            if not release.wait(10):
                raise RuntimeError('Test did not release the model request')
            return fake_model(client, model, data, schema, label, file_input)
        with tempfile.TemporaryDirectory() as temp, patch.object(pdf_study, 'API_KEY', 'test-only'), \
             patch.object(pdf_study, 'request_json', side_effect=waiting_model), contextlib.redirect_stdout(io.StringIO()):
            jobs = StudyJobs(Path(temp), questions=5)
            document_id = str(uuid.uuid4())
            other_id = str(uuid.uuid4())
            other_folder = jobs.folder(other_id)
            other_folder.mkdir()
            (other_folder / 'source.pdf').write_bytes(FIXTURE.read_bytes())
            try:
                jobs.submit(document_id, 'lecture.pdf', FIXTURE.read_bytes())
                self.assertTrue(entered.wait(10))
                jobs.delete(document_id)
                with self.assertRaises(RequestError) as missing:
                    jobs.result(document_id)
                self.assertEqual(missing.exception.status, 404)
                with self.assertRaises(RequestError) as resurrect:
                    jobs.submit(document_id, 'lecture.pdf', FIXTURE.read_bytes())
                self.assertEqual(resurrect.exception.status, 410)
                with self.assertRaises(RequestError):
                    jobs.delete('../outside')
                release.set()
                jobs.pool.shutdown(wait=True)
                self.assertEqual(calls, ['preview_and_abstract'])
                self.assertFalse(jobs.folder(document_id).exists())
                self.assertTrue((other_folder / 'source.pdf').exists())
            finally:
                release.set()
                jobs.pool.shutdown(wait=True)

    def test_server_restart_finishes_pending_deletions(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / str(uuid.uuid4())
            folder.mkdir()
            (folder / '.deleted').write_text('deleted')
            (folder / 'source.pdf').write_bytes(FIXTURE.read_bytes())
            jobs = StudyJobs(Path(temp))
            try:
                self.assertFalse(folder.exists())
            finally:
                jobs.pool.shutdown()

    def test_missing_key_and_interrupted_jobs_are_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            document_id = str(uuid.uuid4())
            folder = directory / document_id
            folder.mkdir()
            pdf_study.write_json(folder / 'result.json', {'id':document_id, 'status':'running', 'documents':[]})
            jobs = StudyJobs(directory)
            try:
                self.assertEqual(jobs.result(document_id)['status'], 'error')
                with patch.object(pdf_study, 'API_KEY', ''):
                    with self.assertRaises(RequestError) as missing:
                        jobs.submit(str(uuid.uuid4()), 'lecture.pdf', FIXTURE.read_bytes())
                self.assertEqual(missing.exception.status, 503)
                self.assertIn('OPENAI_API_KEY', str(missing.exception))
            finally:
                jobs.pool.shutdown()


if __name__ == '__main__':
    unittest.main()
