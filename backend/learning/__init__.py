"""PDF -> summary and flashcards. pdf_study.py is the pipeline, jobs.py runs it, routes.py serves it.

Which pipeline we keep is still open (see CLAUDE.md): everything outside pdf_study.py talks to
it through StudyJobs.runner, so swapping it means replacing one module.
"""
from .jobs import DEFAULT_QUESTIONS, RequestError, StudyJobs  # noqa: F401
from .routes import bp  # noqa: F401
from . import pdf_study  # noqa: F401
