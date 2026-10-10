# Learning pipeline

This package turns an uploaded PDF into a short summary and question-answer flashcards.
`routes.py` exposes the HTTP API, `jobs.py` manages background work, and `pdf_study.py`
contains the model workflow and standalone CLI.

The broader replacement roadmap is documented in [`../learner`](../learner). This file
describes the currently implemented pipeline.

## Processing behavior

The pipeline supports two modes:

- **Shallow** extracts readable PDF text. Pages without extractable text produce an
  actionable error rather than being silently skipped.
- **Deep** sends the complete PDF to the model so it can inspect text, images, charts,
  diagrams, and spatial relationships. It also supports scanned PDFs.

Both modes generate a one-sentence summary and a configurable number of flashcards. Each
mode has independent results and checkpoints, so shallow and deep jobs for the same PDF can
run concurrently. Repeating a completed request is idempotent; an interrupted request can
resume from its saved checkpoint.

Partial summaries and card batches are saved as they complete. Deleting a document prevents
subsequent model requests and removes its files after any active request returns. Cleanup
interrupted by a server restart resumes during application startup.

PDF content is sent to the configured OpenAI-compatible API. Source text and model output are
treated as untrusted data, and API credentials are never included in result files.

## Storage

Each uploaded PDF has one directory under `DATA_DIR/learning`:

```text
<file-id>/source.pdf
<file-id>/<shallow-or-deep>/result.json
<file-id>/<shallow-or-deep>/result.work/<checkpoint>.json
```

Legacy results stored directly at `<file-id>/result.json` remain readable. Writes use atomic
replacement so polling cannot observe partially written JSON.

The result format is:

```json
{
  "id": "file-id",
  "mode": "shallow",
  "status": "complete",
  "requested_sentences": 1,
  "requested_questions": 60,
  "documents": [{
    "abstract": "The lecture explains the main concepts of probability.",
    "sentence_count": 1,
    "requested_sentences": 1,
    "questions": [{
      "question": "What is an event?",
      "answer": "A set of possible outcomes."
    }],
    "complete": true
  }]
}
```

A result may contain an abstract or partial card list while its status is `running`. Failed
jobs retain completed checkpoints and expose a sanitized error for retry.

## HTTP API

All document routes verify that the material belongs to the current user.

- `POST /api/learning/documents/<file-id>` starts or resumes processing. The PDF normally
  already exists in material storage, so the request body is optional.
- `GET /api/learning/documents/<file-id>/result.json?mode=shallow` returns saved progress.
- `DELETE /api/learning/documents/<file-id>` removes every mode and checkpoint.
- `GET /api/learning/health` reports model configuration and pipeline defaults.

Generation requests accept these headers:

- `X-Learning-Mode: shallow|deep`
- `X-Flashcard-Count: 5..300`
- `X-Filename: <encoded PDF name>`

## Configuration

- `OPENAI_MODEL` selects the model.
- `OPENAI_BASE_URL` selects an OpenAI-compatible endpoint.
- `PDF_DEEP_MODE` sets only the standalone CLI default.
- `DEFAULT_QUESTIONS` in `jobs.py` applies when a request omits the count header.
- `SUMMARY_SENTENCES` in `jobs.py` controls the server summary length.

## Standalone CLI

The same workflow can process local PDFs without Flask:

```bash
.venv/bin/python backend/learning/pdf_study.py "slides.pdf" \
  --mode deep --sentences 1 --questions 15 --feedback "" \
  --output study_materials.json
```

The CLI accepts multiple PDFs, a directory, or a quoted wildcard and resumes compatible
partial output. Its interactive preview feedback is automatically accepted by the web job
runner.

## Test coverage

Backend tests use synthetic PDFs and mock the model-response boundary, so they make no API
calls. Coverage includes extraction, sentence correction, checkpoint writes, result polling,
idempotency, concurrent modes, textless PDFs, custom card counts, deletion during generation,
restart cleanup, and missing-key errors.

OpenAI schema reference: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
