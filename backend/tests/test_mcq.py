import json
from unittest import mock
import tempfile
import unittest
import uuid

import db
from learning import mcq
from learning.mcq import fingerprint, validate_questions
from tests.support import build_app


def sample_question(mode="single"):
    correct = [0] if mode == "single" else [0, 1]
    return {"prompt": "Which claim is grounded in the source?",
            "options": ["First claim", "Second claim", "Distractor"],
            "correctOptionIndexes": correct,
            "explanation": "The source supports the selected claim.", "sourcePages": [1]}


class McqValidationTests(unittest.TestCase):
    def test_single_and_multiple_questions_validate(self):
        for mode in ("single", "multiple"):
            result = validate_questions({"questions": [sample_question(mode)]}, {1})
            self.assertEqual(result[0]["selectionMode"], mode)

    def test_invalid_and_duplicate_questions_are_filtered(self):
        duplicate_options = sample_question(); duplicate_options["options"][1] = " first CLAIM "
        invalid_answer = sample_question(); invalid_answer["prompt"] = "Another question?"
        invalid_answer["correctOptionIndexes"] = [5]
        valid = sample_question(); valid["prompt"] = "A useful unique question?"
        result = validate_questions({"questions": [duplicate_options, invalid_answer, valid]}, {1})
        self.assertEqual([question["prompt"] for question in result], ["A useful unique question?"])

    def test_requested_count_is_a_target_and_all_invalid_is_actionable(self):
        result = validate_questions({"questions": [sample_question()]}, {1})
        self.assertEqual(len(result), 1)
        invalid = sample_question(); invalid["sourcePages"] = [99]
        with self.assertRaisesRegex(ValueError, "invalid source pages: 1"):
            validate_questions({"questions": [invalid]}, {1})

    @mock.patch("learning.mcq.pdf_study.request_json")
    @mock.patch("learning.mcq.pdf_study.prepare_source")
    @mock.patch("openai.OpenAI")
    def test_generation_uses_one_model_call(self, openai_client, prepare_source, request_json):
        prepare_source.return_value = {"valid_pages": {1}, "file_input": None, "pages": [{"page": 1}]}
        request_json.return_value = {"questions": [sample_question()]}
        openai_client.return_value.__enter__.return_value = object()
        with mock.patch.object(mcq.pdf_study, "API_KEY", "test-key"):
            result = mcq.generate("slides.pdf", "shallow", requested_count=10)
        self.assertEqual(len(result), 1)
        request_json.assert_called_once()


class McqApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = build_app(self.temp.name, DEV_USER="alice@ethz.ch", DEV_USER_NAME="Alice")
        self.client = self.app.test_client()
        self.material_id = str(uuid.uuid4())
        response = self.client.post("/api/materials", json={"id": self.material_id, "subjectId": "course-1",
            "kind": "pdf", "name": "slides.pdf", "category": "Slides", "marker": "To read"})
        self.assertEqual(response.status_code, 201)

    def tearDown(self):
        self.temp.cleanup()

    def completed_set(self):
        set_id, series_id, question_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        option_ids = [str(uuid.uuid4()) for _ in range(3)]
        with self.app.app_context():
            conn = db.get_db(); user_id = db.get_user_by_email("alice@ethz.ch")["id"]
            with conn:
                conn.execute("""INSERT INTO mcq_sets
                    (id,material_id,user_id,mode,series_id,version,status,idempotency_key)
                    VALUES (?,?,?,?,?,1,'complete',?)""", (set_id, self.material_id, user_id, "shallow", series_id, str(uuid.uuid4())))
                conn.execute("INSERT INTO mcq_questions VALUES (?,?,?,?,?,?,?)",
                    (question_id, set_id, 0, "A grounded question?", "single", "Because the first answer is supported.", "a grounded question"))
                for position, option_id in enumerate(option_ids):
                    conn.execute("INSERT INTO mcq_options VALUES (?,?,?,?,?)",
                                 (option_id, question_id, position, f"Option {position + 1}", int(position == 0)))
                conn.execute("INSERT INTO mcq_question_pages VALUES (?,1)", (question_id,))
        return set_id, question_id, option_ids

    def test_practice_hides_answers_grades_and_is_idempotent(self):
        set_id, question_id, options = self.completed_set()
        started = self.client.post(f"/api/learning/mcq-sets/{set_id}/sessions")
        self.assertEqual(started.status_code, 201)
        session = started.get_json()
        self.assertNotIn("correctOptionIds", session["questions"][0])
        payload = {"questionId": question_id, "selectedOptionIds": [options[0]]}
        first = self.client.post(f"/api/learning/mcq-sessions/{session['id']}/answers", json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.get_json()["correct"])
        self.assertEqual(first.get_json()["sourcePages"], [1])
        self.assertEqual(self.client.post(f"/api/learning/mcq-sessions/{session['id']}/answers", json=payload).status_code, 200)
        conflict = self.client.post(f"/api/learning/mcq-sessions/{session['id']}/answers",
                                    json={"questionId": question_id, "selectedOptionIds": [options[1]]})
        self.assertEqual(conflict.status_code, 409)

    def test_material_deletion_cascades_sets_and_sessions(self):
        set_id, _question_id, _options = self.completed_set()
        self.client.post(f"/api/learning/mcq-sets/{set_id}/sessions")
        self.client.delete(f"/api/materials/{self.material_id}")
        with self.app.app_context():
            self.assertEqual(db.get_db().execute("SELECT count(*) FROM mcq_sets").fetchone()[0], 0)
            self.assertEqual(db.get_db().execute("SELECT count(*) FROM mcq_sessions").fetchone()[0], 0)

    def test_attempt_history_review_and_independent_active_sessions(self):
        set_id, question_id, options = self.completed_set()
        completed = self.client.post(f"/api/learning/mcq-sets/{set_id}/sessions").get_json()
        self.client.post(f"/api/learning/mcq-sessions/{completed['id']}/answers",
                         json={"questionId": question_id, "selectedOptionIds": [options[0]]})
        active_one = self.client.post(f"/api/learning/mcq-sets/{set_id}/sessions").get_json()
        active_two = self.client.post(f"/api/learning/mcq-sets/{set_id}/sessions").get_json()
        self.assertNotEqual(active_one["id"], active_two["id"])

        history = self.client.get(f"/api/learning/mcq-sets/{set_id}/sessions").get_json()
        self.assertEqual(len(history), 3)
        self.assertNotIn("questions", history[0])
        review = self.client.get(f"/api/learning/mcq-sessions/{completed['id']}").get_json()
        self.assertEqual(review["answers"][0]["selectedOptionIds"], [options[0]])
        self.assertEqual(review["answers"][0]["correctOptionIds"], [options[0]])
        self.assertTrue(review["answers"][0]["correct"])


if __name__ == "__main__":
    unittest.main()
