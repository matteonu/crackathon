"""Small, shared data types for document generation and future review flows."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ProcessingMode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"


@dataclass(frozen=True)
class DocumentPage:
    number: int
    text: str
    image: bytes | None = None


@dataclass(frozen=True)
class Card:
    front: str
    back: str
    type: str = "basic"
    source_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class DocumentContext:
    filename: str
    pages: tuple[DocumentPage, ...]
    mode: ProcessingMode


@dataclass(frozen=True)
class GenerationRequest:
    document: DocumentContext
    mode: ProcessingMode
    feedback: Any = None
    target_count: int = 5


@dataclass(frozen=True)
class Exercise:
    prompt: str
    answer: str | None = None
    options: tuple[str, ...] = ()
    type: str = "flashcard"
    source_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class ReviewContext:
    learner_mode: str = "learner"
    context_type: str = "exam"
    metadata: Mapping[str, Any] = field(default_factory=dict)
