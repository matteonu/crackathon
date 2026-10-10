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

<<<<<<< HEAD
Uploading starts a summary-only job: one sentence, using the complete PDF in deep mode.
Summaries use the smaller `gpt-6-luna` model with reasoning disabled by default to reduce
latency. No cards are generated until the user starts processing explicitly; card jobs
use `OPENAI_MODEL` and reuse the saved summary. Both tasks support shallow and deep mode.
Each task/mode has independent results and checkpoints. Repeating a completed request is
idempotent; an interrupted request can resume from its saved checkpoint.
=======
Both modes generate a one-sentence summary and a configurable number of flashcards. Each
mode has independent results and checkpoints, so shallow and deep jobs for the same PDF can
run concurrently. Repeating a completed request is idempotent; an interrupted request can
resume from its saved checkpoint.
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0

Partial summaries and card batches are saved as they complete. Deleting a document prevents
subsequent model requests and removes its files after any active request returns. Cleanup
interrupted by a server restart resumes during application startup.

PDF content is sent to the configured OpenAI-compatible API. Source text and model output are
treated as untrusted data, and API credentials are never included in result files.

## Storage

Each uploaded PDF has one directory under `DATA_DIR/learning`:

```text
<file-id>/source.pdf
<<<<<<< HEAD
<file-id>/summary/<shallow-or-deep>/result.json
=======
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
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
<<<<<<< HEAD
  "task": "flashcards",
  "model": "gpt-6-astra",
=======
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
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

<<<<<<< HEAD
### Document types in SQLite

`materials.kind` stores the format (`pdf`, `md`, `txt`, `folder`, or `deck`). `materials.type`
stores the document's purpose, independently of that format:

| Upload option / legacy category | Stored `type` |
|---|---|
| Slides | `slides` |
| Exercises | `exercise` |
| Solutions | `exercise_solution` |
| Exams | `mock_exam` |
| Scripts | `script` |

Startup adds the column to existing databases and backfills these categories without
removing rows, PDFs, or generated results. Folders have a null type; legacy Notes, Books,
and Transcripts remain unclassified rather than being guessed. The schema also reserves
`summary`, `cards`, and `mcq` from the backend roadmap. Summaries and pipeline checkpoints
use the JSON storage described above; generated flashcards also persist into an independent
deck material and the `flashcards` table, with scheduler progress and review history.

The materials API returns `type`. Create/update requests accept it, derive the matching
display category, and reject invalid or conflicting type/category pairs. Older clients
can still send only `category`; the server assigns its corresponding type. PDF flashcards
are available for `slides`, `exercise_solution`, and `script`; all PDFs can get summaries.

=======
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
## HTTP API

All document routes verify that the material belongs to the current user.

- `POST /api/learning/documents/<file-id>` starts or resumes processing. The PDF normally
  already exists in material storage, so the request body is optional.
<<<<<<< HEAD
- `GET /api/learning/documents/<file-id>/result.json?mode=shallow&task=flashcards` returns saved progress.
=======
- `GET /api/learning/documents/<file-id>/result.json?mode=shallow` returns saved progress.
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
- `DELETE /api/learning/documents/<file-id>` removes every mode and checkpoint.
- `GET /api/learning/health` reports model configuration and pipeline defaults.

Generation requests accept these headers:

- `X-Learning-Mode: shallow|deep`
<<<<<<< HEAD
- `X-Learning-Task: summary|flashcards` (default: `flashcards`)
=======
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
- `X-Flashcard-Count: 5..300`
- `X-Filename: <encoded PDF name>`

## Configuration

<<<<<<< HEAD
- `OPENAI_MODEL` selects the flashcard/standalone CLI model (default: `gpt-6-astra`).
- `OPENAI_SUMMARY_MODEL` selects the upload-summary model (default: `gpt-6-luna`).
- `OPENAI_SUMMARY_REASONING_EFFORT` defaults to `none` for fast summaries. If overriding
  the model, choose a supported effort or set this to empty to omit the reasoning option.
- `/api/learning/health` reports both `model` and `summaryModel`.
=======
- `OPENAI_MODEL` selects the model.
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
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

<<<<<<< HEAD
Document tests cover type validation, upload persistence, category compatibility, and
non-destructive migration of existing libraries. Provider-boundary tests verify that
summary model/settings do not change flashcard requests.

OpenAI schema reference: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Summary model: [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna).
=======
OpenAI schema reference: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
