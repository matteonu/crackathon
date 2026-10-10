"""Context boundaries, owner isolation and durable remote resource lifecycle."""
import base64
from contextlib import closing
from io import BytesIO
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace as Item
import unittest
from unittest.mock import MagicMock
import uuid

import httpx
from openai import NotFoundError
from pypdf import PdfReader, PdfWriter

from learning.document_chat import CHAT_MODEL, CHAT_REASONING_EFFORT, DocumentChat, page_context
from tests.support import build_app
import db

ALICE = {'X-User-Id': 'alice@ethz.ch'}
BOB = {'X-User-Id': 'bob@ethz.ch'}


def missing():
    return NotFoundError('missing', response=httpx.Response(404, request=httpx.Request('GET', 'https://example.test')), body=None)


def pdf_bytes():
    writer = PdfWriter()
    for page in range(1, 6):
        writer.add_blank_page(width=600 + page, height=800)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class Provider:
    def __init__(self):
        self.files, self.stores, self.entries = {}, {}, {}
        self.client = MagicMock()
        self.client.__enter__.return_value = self.client
        self.client.files.list.side_effect = lambda **_: list(self.files.values())
        self.client.vector_stores.list.side_effect = lambda: list(self.stores.values())
        self.client.files.create.side_effect = self.create_file
        self.client.vector_stores.create.side_effect = self.create_store
        self.client.vector_stores.files.retrieve.side_effect = self.retrieve_entry
        self.client.vector_stores.files.create.side_effect = self.create_entry
        self.client.files.delete.side_effect = lambda id: self.files.pop(id, None)
        self.client.vector_stores.delete.side_effect = lambda id: self.stores.pop(id, None)
        self.client.responses.create.return_value = Item(status='completed', output_text='An explanation.', output=[])

    def create_file(self, file, **_):
        row = Item(id='file-' + str(uuid.uuid4()), filename=file[0])
        self.files[row.id] = row
        return row

    def create_store(self, metadata, **_):
        row = Item(id='vs-' + str(uuid.uuid4()), metadata=metadata)
        self.stores[row.id] = row
        return row

    def retrieve_entry(self, file_id, vector_store_id):
        if (vector_store_id, file_id) not in self.entries:
            raise missing()
        return self.entries[vector_store_id, file_id]

    def create_entry(self, vector_store_id, file_id):
        row = Item(status='completed')
        self.entries[vector_store_id, file_id] = row
        return row


class DocumentChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = build_app(self.temp.name)
        self.addCleanup(self.app.extensions['learning_jobs'].pool.shutdown, wait=True)
        self.client = self.app.test_client()
        self.provider = Provider()
        self.service = self.app.extensions['document_chat']
        self.service.client_factory = lambda: self.provider.client

    def create(self, category='Slides', kind='pdf', parent=None, upload=True):
        id = str(uuid.uuid4())
        response = self.client.post('/api/materials', headers=ALICE, json={
            'id': id, 'subjectId': 'analysis', 'kind': kind, 'name': id + '.' + kind,
            'category': category, 'parentId': parent})
        self.assertEqual(response.status_code, 201, response.get_json())
        if upload and kind == 'pdf':
            response = self.client.put(f'/api/materials/{id}/file', headers=ALICE,
                                       content_type='application/pdf', data=pdf_bytes())
            self.assertEqual(response.status_code, 200, response.get_json())
        return id

    def ask(self, id, **overrides):
        body = {'question': 'Explain this.', 'page': 3, 'requestId': str(uuid.uuid4())}
        body.update(overrides)
        return self.client.post(f'/api/learning/documents/{id}/chat', headers=ALICE, json=body)

    def release_retry(self, id):
        with closing(self.service.connect()) as conn, conn:
            conn.execute('UPDATE document_indexes SET next_attempt=0, lease_until=0 WHERE document_id=?', (id,))

    def test_upload_indexes_once_and_ready_index_survives_restart(self):
        id = self.create()
        self.assertEqual(self.service.index(id)['status'], 'queued')
        self.assertTrue(self.service.run_once())
        state = self.service.index(id)
        self.assertEqual(state['status'], 'ready')
        restarted = DocumentChat(self.service.database_path, self.service.directory, lambda: self.provider.client)
        restarted.ensure_index(id)
        self.assertFalse(restarted.run_once())
        self.assertEqual(restarted.index(id)['vector_store_id'], state['vector_store_id'])
        # PUT retries and opening chat don't upload again.
        self.client.put(f'/api/materials/{id}/file', headers=ALICE, content_type='application/pdf', data=pdf_bytes())
        self.client.get(f'/api/learning/documents/{id}/chat', headers=ALICE)
        self.assertFalse(restarted.run_once())
        self.provider.client.files.create.assert_called_once()
        self.provider.client.vector_stores.create.assert_called_once()

    def test_upload_starts_background_indexing_without_opening_chat(self):
        self.service.background = True
        self.addCleanup(self.service.stop)
        id = self.create()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.service.index(id)['status'] != 'ready':
            time.sleep(0.02)
        self.assertEqual(self.service.index(id)['status'], 'ready')
        self.provider.client.files.create.assert_called_once()
        self.provider.client.vector_stores.files.create.assert_called_once()
        self.provider.client.responses.create.assert_not_called()
        # An upload retry wakes the same worker and retains the same index.
        worker = self.service.thread
        self.service.ensure_index(id)
        self.assertIs(self.service.thread, worker)

    def test_chat_uses_shared_provider_config_with_room_to_answer(self):
        id = self.create()
        response = self.ask(id)
        self.assertEqual(response.status_code, 200)
        args = self.provider.client.responses.create.call_args.kwargs
        self.assertEqual(args['model'], CHAT_MODEL)
        if CHAT_REASONING_EFFORT:
            self.assertEqual(args['reasoning'], {'effort': CHAT_REASONING_EFFORT})
        else:
            self.assertNotIn('reasoning', args)
        self.assertGreaterEqual(args['max_output_tokens'], 16000)
        self.assertGreaterEqual(args['timeout'], 180)

    def test_pending_remote_parse_polls_without_reuploading(self):
        id = self.create()
        def pending(**kwargs):
            entry = self.provider.create_entry(**kwargs)
            entry.status = 'in_progress'
            return entry
        self.provider.client.vector_stores.files.create.side_effect = pending
        self.service.run_once()
        self.assertEqual(self.service.index(id)['status'], 'indexing')
        self.release_retry(id)
        self.service.run_once()
        self.provider.client.files.create.assert_called_once()
        self.provider.client.vector_stores.files.create.assert_called_once()
        next(iter(self.provider.entries.values())).status = 'completed'
        self.release_retry(id)
        self.service.run_once()
        self.assertEqual(self.service.index(id)['status'], 'ready')

    def test_current_previous_next_pages_and_edges_are_the_only_attachment(self):
        id = self.create()
        source = self.service.directory / id / 'source.pdf'
        for page, expected in [(1, [1, 2]), (3, [2, 3, 4]), (5, [4, 5])]:
            pages, total, attachment = page_context(source, page)
            self.assertEqual((pages, total), (expected, 5))
            decoded = PdfReader(BytesIO(base64.b64decode(attachment['file_data'].split(',')[1])))
            self.assertEqual([int(p.mediabox.width) for p in decoded.pages], [600 + n for n in expected])

    def test_chat_is_owner_scoped_and_rejects_unsupported_types(self):
        for category in ['Slides', 'Solutions', 'Scripts', 'Exams']:
            id = self.create(category=category)
            self.assertEqual(self.client.get(f'/api/learning/documents/{id}/chat', headers=ALICE).status_code, 200)
            for method in [self.client.get, self.client.post]:
                self.assertEqual(method(f'/api/learning/documents/{id}/chat', headers=BOB).status_code, 404)
            self.assertEqual(self.client.post(f'/api/learning/documents/{id}/chat/index', headers=BOB).status_code, 404)
        for category in ['Exercises', 'Books', 'Notes']:
            id = self.create(category=category)
            self.assertEqual(self.client.get(f'/api/learning/documents/{id}/chat', headers=ALICE).status_code, 400)
            self.assertEqual(self.service.index(id)['status'], 'queued')  # All uploads indexed.

    def test_request_validation_does_not_call_the_model(self):
        id = self.create()
        for fields in [{'page': 0}, {'page': 6}, {'page': True}, {'page': '3'}, {'question': ''},
                       {'question': 'a' * 4001}, {'question': []}, {'requestId': 'invalid'}]:
            self.assertEqual(self.ask(id, **fields).status_code, 400, fields)
        self.assertEqual(self.client.post(f'/api/learning/documents/{id}/chat', headers=ALICE, json=[]).status_code, 400)
        self.provider.client.responses.create.assert_not_called()

    def test_local_page_chat_works_while_indexing_without_search_tool(self):
        id = self.create()
        result = self.ask(id)
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual(result.get_json()['pages'], [2, 3, 4])
        args = self.provider.client.responses.create.call_args.kwargs
        self.assertEqual(args['tools'], [])
        self.assertFalse(args['store'])
        self.assertIn('Attached pages, in order: [2, 3, 4]', args['instructions'])

    def test_search_can_only_use_this_documents_index(self):
        id = self.create()
        other = self.create()
        self.service.run_once()
        self.service.run_once()
        self.provider.client.responses.create.return_value.output = [Item(type='file_search_call')]
        answer = self.ask(id).get_json()
        args = self.provider.client.responses.create.call_args.kwargs
        self.assertEqual(args['tools'][0]['vector_store_ids'], [self.service.index(id)['vector_store_id']])
        self.assertNotIn(self.service.index(other)['vector_store_id'], repr(args))
        self.assertTrue(answer['searchedDocument'])
        self.assertEqual(args['tool_choice'], 'auto')

    def test_history_persists_but_old_page_attachments_are_not_replayed(self):
        id = self.create()
        first = self.ask(id, page=1).get_json()
        second = self.ask(id, page=5).get_json()
        inputs = self.provider.client.responses.create.call_args.kwargs['input']
        self.assertEqual(len(inputs), 3)
        self.assertEqual(inputs[1]['content'], first['answer'])
        self.assertIsInstance(inputs[0]['content'], str)
        attachment = inputs[-1]['content'][0]
        pdf = PdfReader(BytesIO(base64.b64decode(attachment['file_data'].split(',')[1])))
        self.assertEqual([int(p.mediabox.width) for p in pdf.pages], [604, 605])
        restarted = DocumentChat(self.service.database_path, self.service.directory)
        self.assertEqual(restarted.history(id), [first, second])

    def test_retried_question_does_not_duplicate_saved_turn(self):
        id = self.create()
        request_id = str(uuid.uuid4())
        first = self.ask(id, requestId=request_id).get_json()
        self.assertEqual(self.ask(id, requestId=request_id).get_json(), first)
        self.provider.client.responses.create.assert_called_once()
        self.assertEqual(len(self.service.history(id)), 1)

    def test_delete_clears_history_and_both_remote_resources(self):
        id = self.create()
        self.service.run_once()
        self.ask(id)
        self.assertEqual(self.client.delete(f'/api/materials/{id}', headers=ALICE).status_code, 200)
        self.assertEqual(self.service.index(id)['status'], 'deleting')
        self.assertEqual(self.service.history(id), [])
        self.assertEqual(self.ask(id).status_code, 404)
        self.service.run_once()
        self.assertEqual(self.service.index(id)['status'], 'deleted')
        self.assertEqual((self.provider.files, self.provider.stores), ({}, {}))

    def test_folder_cascade_queues_every_document_context_for_cleanup(self):
        folder = self.create(kind='folder', upload=False)
        nested = self.create(kind='folder', parent=folder, upload=False)
        docs = [self.create(parent=folder), self.create(parent=nested)]
        for _ in docs:
            self.service.run_once()
        self.client.delete(f'/api/materials/{folder}', headers=ALICE)
        for id in docs:
            self.assertEqual(self.service.index(id)['status'], 'deleting')
            self.service.run_once()
        self.assertFalse(self.provider.files or self.provider.stores)

    def test_failed_cleanup_is_durable_and_retried_after_restart(self):
        id = self.create()
        self.service.run_once()
        self.client.delete(f'/api/materials/{id}', headers=ALICE)
        remove_file = self.provider.client.files.delete.side_effect
        self.provider.client.files.delete.side_effect = RuntimeError('network unavailable')
        self.service.run_once()
        self.assertEqual(self.service.index(id)['status'], 'deleting')
        self.assertTrue(self.service.index(id)['file_id'])
        self.provider.client.files.delete.side_effect = remove_file
        restarted = DocumentChat(self.service.database_path, self.service.directory, lambda: self.provider.client)
        self.release_retry(id)
        restarted.run_once()
        self.assertEqual(restarted.index(id)['status'], 'deleted')
        self.assertFalse(self.provider.files or self.provider.stores)

    def test_delete_during_file_upload_retains_remote_id_for_cleanup(self):
        id = self.create()
        def racing_upload(**kwargs):
            result = self.provider.create_file(**kwargs)
            self.client.delete(f'/api/materials/{id}', headers=ALICE)
            return result
        self.provider.client.files.create.side_effect = racing_upload
        self.service.run_once()
        state = self.service.index(id)
        self.assertEqual(state['status'], 'deleting')
        self.assertTrue(state['file_id'])
        self.provider.client.vector_stores.create.assert_not_called()
        self.service.run_once()
        self.assertFalse(self.provider.files)

    def test_remote_resources_are_recovered_after_a_lost_response(self):
        id = self.create()
        state = self.service.index(id)
        remote_file = self.provider.create_file(file=('study-' + state['resource_key'] + '.pdf', None))
        remote_store = self.provider.create_store(metadata={'resource_key': state['resource_key']})
        self.service.run_once()
        self.assertEqual(self.service.index(id)['file_id'], remote_file.id)
        self.assertEqual(self.service.index(id)['vector_store_id'], remote_store.id)
        self.provider.client.files.create.assert_not_called()
        self.provider.client.vector_stores.create.assert_not_called()

    def test_delete_recovers_resources_whose_ids_were_not_saved(self):
        id = self.create()
        state = self.service.index(id)
        self.provider.create_file(file=('study-' + state['resource_key'] + '.pdf', None))
        self.provider.create_store(metadata={'resource_key': state['resource_key']})
        self.client.delete(f'/api/materials/{id}', headers=ALICE)
        self.service.run_once()
        self.assertFalse(self.provider.files or self.provider.stores)

    def test_delete_during_answer_prevents_returning_or_saving_the_response(self):
        id = self.create()
        def racing_answer(**_):
            self.client.delete(f'/api/materials/{id}', headers=ALICE)
            return Item(status='completed', output_text='Late answer', output=[])
        self.provider.client.responses.create.side_effect = racing_answer
        self.assertEqual(self.ask(id).status_code, 404)
        self.assertEqual(self.service.history(id), [])

    def test_two_workers_cannot_index_the_same_document_concurrently(self):
        id = self.create()
        entered, release = threading.Event(), threading.Event()
        def slow_upload(**kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return self.provider.create_file(**kwargs)
        self.provider.client.files.create.side_effect = slow_upload
        worker = threading.Thread(target=self.service.run_once)
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            restarted = DocumentChat(self.service.database_path, self.service.directory, lambda: self.provider.client)
            self.assertFalse(restarted.run_once())
        finally:
            release.set()
            worker.join(5)
        self.assertEqual(self.service.index(id)['status'], 'ready')
        self.provider.client.files.create.assert_called_once()

    def test_errors_hide_provider_details_and_index_can_be_retried(self):
        id = self.create()
        self.provider.client.files.create.side_effect = RuntimeError('SECRET / raw provider payload')
        for _ in range(3):
            self.release_retry(id)
            self.service.run_once()
        state = self.client.get(f'/api/learning/documents/{id}/chat', headers=ALICE).get_json()
        self.assertEqual(state['index']['status'], 'error')
        self.assertNotIn('SECRET', str(state))
        self.assertEqual(self.client.post(f'/api/learning/documents/{id}/chat/index', headers=ALICE).status_code, 202)
        self.provider.client.files.create.side_effect = self.provider.create_file
        self.service.run_once()
        self.assertEqual(self.service.index(id)['status'], 'ready')
        self.provider.client.responses.create.side_effect = RuntimeError('SECRET')
        response = self.ask(id)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('SECRET', response.get_data(as_text=True))

    def test_database_reset_preserves_remote_cleanup_queue(self):
        id = self.create()
        self.service.run_once()
        with self.app.app_context():
            db.reset_db()
        self.assertEqual(self.service.index(id)['status'], 'deleting')
        self.service.run_once()
        self.assertFalse(self.provider.files or self.provider.stores)


if __name__ == '__main__':
    unittest.main()
