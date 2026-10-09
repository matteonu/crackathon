"""PDF validation, extraction, sampling, and rendering."""

from __future__ import annotations

import io
from typing import Iterable

from .models import DocumentPage, ProcessingMode


class PDFError(ValueError):
    """Raised when a PDF cannot be safely processed."""


def validate_pdf(data: bytes, *, max_bytes: int = 50 * 1024 * 1024) -> None:
    if not data or len(data) > max_bytes or not data.startswith(b"%PDF-"):
        raise PDFError("The uploaded file is not a valid PDF or is too large.")
    try:
        from pypdf import PdfReader

        PdfReader(io.BytesIO(data), strict=False)
    except ImportError as exc:
        raise PDFError("PDF support is not installed.") from exc
    except Exception as exc:
        raise PDFError("The uploaded PDF could not be read.") from exc


def extract_text(data: bytes) -> tuple[DocumentPage, ...]:
    validate_pdf(data)
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=False)
        return tuple(
            DocumentPage(number=index + 1, text=(page.extract_text() or "").strip())
            for index, page in enumerate(reader.pages)
        )
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError("Text could not be extracted from the PDF.") from exc


def representative_pages(pages: Iterable[DocumentPage], limit: int = 8) -> tuple[DocumentPage, ...]:
    pages = tuple(pages)
    if len(pages) <= limit:
        return pages
    indexes = {round(i * (len(pages) - 1) / (limit - 1)) for i in range(limit)}
    return tuple(pages[index] for index in sorted(indexes))


def render_pages(data: bytes, pages: Iterable[DocumentPage] | None = None) -> tuple[DocumentPage, ...]:
    """Render selected pages as PNG bytes, preserving extracted text."""
    text_pages = tuple(pages or extract_text(data))
    try:
        import fitz

        document = fitz.open(stream=data, filetype="pdf")
        rendered = []
        for page in text_pages:
            image = document.load_page(page.number - 1).get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
            rendered.append(DocumentPage(page.number, page.text, image))
        document.close()
        return tuple(rendered)
    except ImportError as exc:
        raise PDFError("PDF rendering support is not installed.") from exc
    except Exception as exc:
        raise PDFError("The PDF pages could not be rendered.") from exc


def prepare_pages(data: bytes, mode: ProcessingMode) -> tuple[DocumentPage, ...]:
    pages = extract_text(data)
    if mode == ProcessingMode.QUICK:
        return representative_pages(pages)
    return render_pages(data, pages)
