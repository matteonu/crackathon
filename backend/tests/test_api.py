import base64
import io
import os
import tempfile
import unittest
import zipfile
from unittest.mock import Mock

from studyapp import create_app, db
from studyapp.flashcards.engine.engine import DocumentEngine


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE_PATH": os.path.join(self.tmp.name, "app.db"),
        })
        with self.app.app_context():
            db.reset_db()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, password="alice123"):
        return self.client.post("/api/login", json={"username": "alice", "password": password})

    def test_login(self):
        self.assertEqual(self.login("wrong").status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/me").get_json(), {"username": "alice"})

    def test_dashboard_requires_login(self):
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)
        self.login()
        data = self.client.get("/api/dashboard").get_json()
        self.assertEqual(data["user"]["username"], "alice")
        self.assertTrue(data["semesters"])

    def test_flashcards_require_login(self):
        for path in ("/api/flashcards/examples", "/api/flashcards/final", "/api/flashcards/export"):
            self.assertEqual(self.client.post(path, json={}).status_code, 401, path)

    def test_examples_uses_engine(self):
        model = Mock(model="test-model")
        model.generate_json.return_value = {"cards": [{"front": "Q", "back": "A", "source_pages": [1]}]}
        self.app.extensions["flashcards_engine"] = DocumentEngine(model)
        self.login()
        pdf = _tiny_pdf()
        res = self.client.post("/api/flashcards/examples", json={"filename": "x.pdf", "pdfBase64": base64.b64encode(pdf).decode()})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(res.get_json()["cards"], [{"front": "Q", "back": "A", "type": "basic", "source_pages": [1]}])

    def test_bad_pdf_is_a_400(self):
        self.login()
        res = self.client.post("/api/flashcards/examples", json={"pdfBase64": "bm90IGEgcGRm"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_export_returns_apkg(self):
        self.login()
        res = self.client.post("/api/flashcards/export", json={"deckName": "T", "cards": [{"front": "Q", "back": "A"}]})
        self.assertEqual(res.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(res.data)) as archive:
            self.assertIn("collection.anki2", archive.namelist())

    def test_spa_fallback(self):
        # Unknown paths serve the Angular index.html (or 404 when the frontend isn't built).
        with self.client.get("/flashcards") as res:
            self.assertIn(res.status_code, (200, 404))


def _tiny_pdf():
    """A one-page PDF with some text, built with PyMuPDF."""
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Hello flashcards")
    data = doc.tobytes()
    doc.close()
    return data


if __name__ == "__main__":
    unittest.main()
