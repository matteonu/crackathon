"""Stable document types, separate from file format and legacy display categories."""

CATEGORY_TYPES = {
    "Slides": "slides",
    "Exams": "mock_exam",
    "Exercises": "exercise",
    "Solutions": "exercise_solution",
    "Scripts": "script",
}
TYPE_CATEGORIES = {value: key for key, value in CATEGORY_TYPES.items()}
# Reserved artifact types from the learning backend plan. Generation still saves
# results in the existing JSON files; this change does not create artifact rows.
TYPE_CATEGORIES.update(summary="Notes", cards="Notes", mcq="Notes")
DOCUMENT_TYPES = frozenset(TYPE_CATEGORIES)
FLASHCARD_TYPES = {"slides", "exercise_solution", "script"}


def migrate_material_types(conn):
    """Upgrade existing libraries in place, including older seed data."""
    if "type" not in {row["name"] for row in conn.execute("PRAGMA table_info(materials)")}:
        allowed = ", ".join(f"'{value}'" for value in sorted(DOCUMENT_TYPES))
        conn.execute(f"ALTER TABLE materials ADD COLUMN type TEXT "
                     f"CHECK (type IS NULL OR (type IN ({allowed}) AND kind <> 'folder'))")
    # Preserve explicit classifications. Legacy notes/books/transcripts have no
    # unambiguous source type, and folders are containers rather than documents.
    for category, document_type in CATEGORY_TYPES.items():
        conn.execute("UPDATE materials SET type = ? WHERE type IS NULL AND kind <> 'folder' AND category = ?",
                     (document_type, category))
