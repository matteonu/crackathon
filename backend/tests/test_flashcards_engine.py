import unittest
import zipfile
from unittest.mock import Mock, patch

from studyapp.flashcards.engine.anki import export_apkg
from studyapp.flashcards.engine.engine import DocumentEngine, validate_cards
from studyapp.flashcards.engine.models import Card, DocumentPage, ProcessingMode


class DocumentEngineTests(unittest.TestCase):
    def test_cards_are_normalized_and_deduplicated(self):
        cards = validate_cards({"cards": [
            {"front": " What is X? ", "back": " A thing. "},
            {"front": "what is x?", "back": "a thing."},
            {"front": "", "back": "ignored"},
        ]})
        self.assertEqual(cards, [Card("What is X?", "A thing.")])

    def test_mode_is_passed_to_context_and_feedback_to_model(self):
        client = Mock()
        client.generate_json.return_value = {"cards": [{"front": "Q", "back": "A"}]}
        engine = DocumentEngine(client)
        with patch("studyapp.flashcards.engine.engine.pdf.prepare_pages", return_value=(DocumentPage(1, "text"),)) as prepare:
            examples = engine.generate_examples(b"pdf", "slides.pdf", ProcessingMode.DEEP)
            final = engine.generate_final_deck(b"pdf", {"overall": "More detail"}, filename="slides.pdf", mode=ProcessingMode.QUICK)
        self.assertEqual(len(examples), 1)
        self.assertEqual(len(final), 1)
        self.assertEqual(prepare.call_args_list[0].args[1], ProcessingMode.DEEP)
        self.assertEqual(client.generate_json.call_args_list[1].kwargs["feedback"], {"overall": "More detail"})

    def test_apkg_contains_collection(self):
        first = export_apkg([Card("Q", "A")], "Test")
        second = export_apkg([Card("Q", "A")], "Test")
        self.assertEqual(first, second)
        with zipfile.ZipFile(__import__("io").BytesIO(first)) as archive:
            self.assertIn("collection.anki2", archive.namelist())


if __name__ == "__main__":
    unittest.main()
