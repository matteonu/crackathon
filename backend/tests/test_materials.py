"""The file library: what a caller can see, change and upload, and what belongs to whom."""
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import uuid

from learning.jobs import StudyJobs
from tests.support import build_app

FIXTURE = Path(__file__).resolve().parents[2] / 'frontend/tests/fixtures/study-demo.pdf'
ALICE = {'X-User-Id': 'alice@ethz.ch'}
BOB = {'X-User-Id': 'bob@ethz.ch'}


def body(**overrides):
    data = {'id': str(uuid.uuid4()), 'subjectId': 'analysis', 'kind': 'pdf',
            'name': 'lecture.pdf', 'category': 'Slides'}
    data.update(overrides)
    return data


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = build_app(self.temp.name)
        self.addCleanup(self.app.extensions['learning_jobs'].pool.shutdown, wait=True)
        self.client = self.app.test_client()

    def create(self, headers=ALICE, **overrides):
        response = self.client.post('/api/materials', json=body(**overrides), headers=headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def test_a_created_file_comes_back_in_the_listing(self):
        created = self.create(name='week1', kind='folder', category='Notes')
        self.assertEqual(created['kind'], 'folder')
        listed = self.client.get('/api/materials', headers=ALICE).get_json()
        self.assertEqual([f['id'] for f in listed], [created['id']])
        self.assertEqual(self.client.get('/api/materials?subject=other', headers=ALICE).get_json(), [])

    def test_files_are_private_to_their_owner(self):
        created = self.create()
        self.assertEqual(self.client.get(f"/api/materials/{created['id']}", headers=ALICE).get_json(), created)
        self.assertEqual(self.client.get('/api/materials', headers=BOB).get_json(), [])
        for method, path in ((self.client.get, f"/api/materials/{created['id']}"),
                             (self.client.get, f"/api/materials/{created['id']}/file"),
                             (self.client.delete, f"/api/materials/{created['id']}"),
                             (self.client.get, f"/api/learning/documents/{created['id']}/result.json")):
            self.assertEqual(method(path, headers=BOB).status_code, 404, path)
        patched = self.client.patch(f"/api/materials/{created['id']}", json={'marker': 'Done'}, headers=BOB)
        self.assertEqual(patched.status_code, 404)

    def test_one_name_per_folder_ignoring_case(self):
        folder = self.create(name='week1', kind='folder', category='Notes')
        self.create(name='lecture.pdf')
        clash = self.client.post('/api/materials', json=body(name='LECTURE.pdf'), headers=ALICE)
        self.assertEqual((clash.status_code, clash.get_json()['error']),
                         (409, 'That name already exists in this folder.'))
        # The same name inside a folder is a different place, and so is another user's root.
        self.create(name='lecture.pdf', parentId=folder['id'])
        self.create(name='lecture.pdf', headers=BOB)

    def test_a_parent_must_be_a_folder_in_the_same_subject(self):
        pdf = self.create(name='lecture.pdf')
        other_subject = self.create(name='algebra-folder', kind='folder', category='Notes', subjectId='algebra')
        for parent in (pdf['id'], other_subject['id'], str(uuid.uuid4())):
            response = self.client.post('/api/materials', json=body(name='notes.md', kind='md', content='',
                                                                    category='Notes', parentId=parent), headers=ALICE)
            self.assertEqual((parent, response.status_code), (parent, 400))

    def test_a_folder_cannot_be_moved_into_itself(self):
        outer = self.create(name='week1', kind='folder', category='Notes')
        inner = self.create(name='lecture', kind='folder', category='Notes', parentId=outer['id'])
        response = self.client.patch(f"/api/materials/{outer['id']}", json={'parentId': inner['id']}, headers=ALICE)
        self.assertEqual((response.status_code, response.get_json()['error']),
                         (400, 'A folder cannot contain itself.'))

    def test_a_note_keeps_its_text_and_its_size(self):
        note = self.create(name='summary.md', kind='md', content='# Title\n', category='Notes')
        self.assertEqual((note['content'], note['size']), ('# Title\n', 8))
        updated = self.client.patch(f"/api/materials/{note['id']}", json={'content': 'longer text'},
                                    headers=ALICE).get_json()
        self.assertEqual((updated['content'], updated['size']), ('longer text', 11))
        self.assertEqual(self.client.get(f"/api/materials/{note['id']}/file", headers=ALICE).text, 'longer text')

    def test_only_text_files_can_be_edited_as_text(self):
        pdf = self.create()
        response = self.client.patch(f"/api/materials/{pdf['id']}", json={'content': 'nope'}, headers=ALICE)
        self.assertEqual((response.status_code, response.get_json()['error']),
                         (400, 'Only text files can be edited.'))

    def test_outputs_and_processing_are_stored_as_sent(self):
        pdf = self.create()
        outputs = {'summary': {'text': 'One sentence.'},
                   'flashcards': {'cards': [{'id': 'c1', 'question': 'Q', 'answer': 'A', 'generated': True}]}}
        updated = self.client.patch(f"/api/materials/{pdf['id']}",
                                    json={'outputs': outputs, 'processing': {'status': 'complete', 'mode': 'deep'}},
                                    headers=ALICE).get_json()
        self.assertEqual(updated['outputs'], outputs)
        self.assertEqual(updated['processing'], {'status': 'complete', 'mode': 'deep'})
        self.assertEqual(self.client.get('/api/materials', headers=ALICE).get_json()[0]['outputs'], outputs)

    def test_a_pdf_is_uploaded_once_and_served_back(self):
        pdf = self.create()
        url = f"/api/materials/{pdf['id']}/file"
        self.assertEqual(self.client.get(url, headers=ALICE).status_code, 404)
        # Processing before the upload says so instead of starting a run.
        pending = self.client.post(f"/api/learning/documents/{pdf['id']}", headers=ALICE)
        self.assertEqual((pending.status_code, pending.get_json()['error']),
                         (404, 'Upload the PDF before processing it.'))
        uploaded = self.client.put(url, data=FIXTURE.read_bytes(), content_type='application/pdf', headers=ALICE)
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.get_json()['size'], FIXTURE.stat().st_size)
        served = self.client.get(url, headers=ALICE)
        self.addCleanup(served.close)
        self.assertEqual((served.status_code, served.data), (200, FIXTURE.read_bytes()))
        self.assertEqual(served.headers['Content-Type'], 'application/pdf')

    def test_uploads_are_validated(self):
        pdf = self.create()
        url = f"/api/materials/{pdf['id']}/file"
        self.assertEqual(self.client.put(url, data=b'%PDF-ok', content_type='text/plain', headers=ALICE).status_code, 415)
        self.assertEqual(self.client.put(url, data=b'not a pdf', content_type='application/pdf', headers=ALICE).status_code, 400)
        self.assertEqual(self.client.put(url, data=b'', content_type='application/pdf', headers=ALICE).status_code, 413)
        folder = self.create(name='week1', kind='folder', category='Notes')
        self.assertEqual(self.client.put(f"/api/materials/{folder['id']}/file", data=b'%PDF-1.4',
                                         content_type='application/pdf', headers=ALICE).status_code, 400)

    def test_deleting_a_folder_removes_what_is_inside_it_and_the_stored_pdf(self):
        folder = self.create(name='week1', kind='folder', category='Notes')
        nested = self.create(name='slides', kind='folder', category='Notes', parentId=folder['id'])
        note = self.create(name='notes.txt', kind='txt', content='Notes', category='Notes', parentId=folder['id'])
        pdf = self.create(name='lecture.pdf', parentId=nested['id'])
        sibling = self.create(name='keep.txt', kind='txt', content='', category='Notes')
        self.client.put(f"/api/materials/{pdf['id']}/file", data=FIXTURE.read_bytes(),
                        content_type='application/pdf', headers=ALICE)
        stored = Path(self.temp.name) / 'learning' / pdf['id']
        self.assertTrue((stored / 'source.pdf').exists())
        deleted = self.client.delete(f"/api/materials/{folder['id']}", headers=ALICE)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(set(deleted.get_json()['deleted']), {folder['id'], nested['id'], note['id'], pdf['id']})
        self.assertEqual(self.client.get('/api/materials', headers=ALICE).get_json(), [sibling])
        self.assertEqual(self.client.get(f"/api/materials/{pdf['id']}", headers=ALICE).status_code, 404)
        self.assertFalse(stored.exists())

    def test_readonly_pdf_and_folder_are_removed_without_a_ghost_row(self):
        pdf = self.create()
        jobs = self.app.extensions['learning_jobs']
        jobs.store_source(pdf['id'], FIXTURE.read_bytes())
        folder = jobs.folder(pdf['id'])
        source = jobs.source_path(pdf['id'])
        generated = folder / 'deep'
        generated.mkdir()
        result = generated / 'result.json'
        result.write_text('{"status":"complete","documents":[]}', encoding='utf-8')
        result.chmod(stat.S_IREAD)
        generated.chmod(stat.S_IREAD | stat.S_IEXEC)
        source.chmod(stat.S_IREAD)
        folder.chmod(stat.S_IREAD | stat.S_IEXEC)
        try:
            response = self.client.delete(f"/api/materials/{pdf['id']}", headers=ALICE)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get('/api/materials', headers=ALICE).get_json(), [])
            self.assertFalse(folder.exists())
        finally:
            for path in (folder, generated, source, result):
                if path.exists():
                    path.chmod(path.stat().st_mode | stat.S_IWRITE)

    def test_locked_pdf_does_not_fail_folder_deletion_and_is_cleaned_on_restart(self):
        folder = self.create(name='week1', kind='folder', category='Notes')
        locked = self.create(name='locked.pdf', parentId=folder['id'])
        unlocked = self.create(name='unlocked.pdf', parentId=folder['id'])
        jobs = self.app.extensions['learning_jobs']
        for pdf in (locked, unlocked):
            jobs.store_source(pdf['id'], FIXTURE.read_bytes())
        remove = jobs.remove_folder
        def locked_cleanup(document_id):
            if document_id == locked['id']:
                raise PermissionError('PDF is still open')
            remove(document_id)
        with patch.object(jobs, 'remove_folder', side_effect=locked_cleanup):
            response = self.client.delete(f"/api/materials/{folder['id']}", headers=ALICE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()['deleted']), {folder['id'], locked['id'], unlocked['id']})
        self.assertEqual(self.client.get('/api/materials', headers=ALICE).get_json(), [])
        self.assertEqual(self.client.get(f"/api/materials/{locked['id']}", headers=ALICE).status_code, 404)
        self.assertEqual(self.client.get(f"/api/materials/{locked['id']}/file", headers=ALICE).status_code, 404)
        self.assertFalse(jobs.folder(unlocked['id']).exists())
        self.assertTrue(jobs.folder(locked['id']).exists())
        self.assertTrue(jobs.deletion_marker(locked['id']).exists())
        restarted = StudyJobs(jobs.directory)
        self.addCleanup(restarted.pool.shutdown, wait=True)
        self.assertFalse(jobs.folder(locked['id']).exists())
        self.assertFalse(jobs.deletion_marker(locked['id']).exists())

    def test_a_malformed_file_is_refused(self):
        for overrides, field in ((dict(kind='exe'), 'kind'), (dict(name='a/b.pdf'), 'name'),
                                 (dict(name=''), 'name'), (dict(category='Random'), 'category'),
                                 (dict(subjectId=''), 'subject'), (dict(id='not-a-uuid'), 'id'),
                                 (dict(name='notes.md', kind='md', content='x' * 200_001, category='Notes'), 'content')):
            response = self.client.post('/api/materials', json=body(**overrides), headers=ALICE)
            self.assertEqual(response.status_code, 400, (field, response.get_json()))


if __name__ == '__main__':
    unittest.main()
