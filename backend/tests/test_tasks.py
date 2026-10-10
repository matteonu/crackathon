"""Per-subject task lists: what a caller can add, tick off, edit and delete, and whose they are."""
import tempfile
import unittest
import uuid

from tests.support import build_app

ALICE = {'X-User-Id': 'alice@ethz.ch'}
BOB = {'X-User-Id': 'bob@ethz.ch'}


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = build_app(self.temp.name).test_client()

    def create(self, title='Read chapter 3', subject='analysis', headers=ALICE, **extra):
        body = {'id': str(uuid.uuid4()), 'subjectId': subject, 'title': title, **extra}
        response = self.client.post('/api/tasks', json=body, headers=headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def titles(self, subject=None, headers=ALICE):
        query = f'?subject={subject}' if subject else ''
        return [t['title'] for t in self.client.get('/api/tasks' + query, headers=headers).get_json()]

    def test_new_tasks_go_to_the_top_of_their_subject(self):
        self.create('first')
        self.create('second')
        self.create('elsewhere', subject='algebra')
        self.assertEqual(self.titles('analysis'), ['second', 'first'])
        self.assertEqual(sorted(self.titles()), ['elsewhere', 'first', 'second'])   # order is only meaningful per subject
        created = self.create('with details', notes='  see slides  ', due='2026-11-30')
        self.assertEqual((created['notes'], created['due'], created['done'], created['completedAt']),
                         ('see slides', '2026-11-30', False, None))

    def test_ticking_off_moves_a_task_below_the_open_ones_and_back(self):
        first = self.create('first')
        self.create('second')
        done = self.client.patch(f"/api/tasks/{first['id']}", json={'done': True}, headers=ALICE).get_json()
        self.assertTrue(done['done'])
        self.assertIsInstance(done['completedAt'], int)
        self.assertEqual(self.titles('analysis'), ['second', 'first'])
        reopened = self.client.patch(f"/api/tasks/{first['id']}", json={'done': False}, headers=ALICE).get_json()
        self.assertEqual((reopened['done'], reopened['completedAt']), (False, None))

    def test_editing_title_notes_due_and_position(self):
        task = self.create('draft')
        edited = self.client.patch(f"/api/tasks/{task['id']}",
                                   json={'title': '  Solve   sheet 4 ', 'notes': 'Q1-Q5', 'due': '2026-12-01', 'position': 7.5},
                                   headers=ALICE).get_json()
        self.assertEqual((edited['title'], edited['notes'], edited['due'], edited['position']),
                         ('Solve sheet 4', 'Q1-Q5', '2026-12-01', 7.5))
        cleared = self.client.patch(f"/api/tasks/{task['id']}", json={'due': None}, headers=ALICE).get_json()
        self.assertIsNone(cleared['due'])

    def test_bad_input_is_refused(self):
        for body, message in ((dict(title='   '), 'Use a title of 1-500 characters.'),
                              (dict(title='x' * 501), 'Use a title of 1-500 characters.'),
                              (dict(title='ok', due='next week'), 'Use a due date like 2026-11-30.'),
                              (dict(title='ok', notes='n' * 5001), 'These notes are too long to save.'),
                              (dict(title='ok', subjectId=''), 'This task needs a subject.'),
                              (dict(title='ok', id='nope'), 'Invalid task ID.')):
            data = {'id': str(uuid.uuid4()), 'subjectId': 'analysis', **body}
            response = self.client.post('/api/tasks', json=data, headers=ALICE)
            self.assertEqual((response.status_code, response.get_json()['error']), (400, message), body)
        task = self.create()
        response = self.client.patch(f"/api/tasks/{task['id']}", json={'done': 'yes'}, headers=ALICE)
        self.assertEqual(response.status_code, 400)

    def test_tasks_are_private_to_their_owner(self):
        task = self.create()
        self.assertEqual(self.titles(headers=BOB), [])
        self.assertEqual(self.client.patch(f"/api/tasks/{task['id']}", json={'done': True}, headers=BOB).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/tasks/{task['id']}", headers=BOB).status_code, 404)
        self.assertEqual(self.client.get('/api/tasks').status_code, 401)
        self.assertEqual(self.titles(), ['Read chapter 3'])

    def test_delete_one_and_clear_completed(self):
        keep = self.create('keep')
        gone = self.create('gone')
        done_a = self.create('done a')
        done_b = self.create('done b')
        self.create('done elsewhere', subject='algebra')
        for t in (done_a, done_b):
            self.client.patch(f"/api/tasks/{t['id']}", json={'done': True}, headers=ALICE)
        self.client.patch("/api/tasks/" + self.client.get('/api/tasks?subject=algebra', headers=ALICE).get_json()[0]['id'],
                          json={'done': True}, headers=ALICE)
        self.assertEqual(self.client.delete(f"/api/tasks/{gone['id']}", headers=ALICE).status_code, 204)
        self.assertEqual(self.client.delete(f"/api/tasks/{gone['id']}", headers=ALICE).status_code, 404)
        self.assertEqual(self.client.delete('/api/tasks/completed?subject=analysis', headers=ALICE).get_json(), {'deleted': 2})
        self.assertEqual(self.titles('analysis'), [keep['title']])
        self.assertEqual(self.titles('algebra'), ['done elsewhere'])   # another subject's done tasks stay
        self.assertEqual(self.client.delete('/api/tasks/completed', headers=ALICE).status_code, 400)


if __name__ == '__main__':
    unittest.main()
