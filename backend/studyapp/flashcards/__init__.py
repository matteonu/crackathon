"""Lecture PDF -> example cards -> feedback -> final flashcards -> Anki deck.

routes.py is the HTTP layer; engine/ holds the logic (see engine/AGENTS.md).
"""
from .routes import bp

__all__ = ["bp"]
