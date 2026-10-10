# Integrated learning view

This branch copies the full frontend, including the simplified Materials layout, and
connects the subject file viewer to the adapted `learning_backend/pdf_study.py`.

## Run in Git Bash

From this repository folder:

```bash
bash start-learning.sh
```

The launcher installs the Python dependencies, installs frontend packages if needed,
and builds Angular. It uses `OPENAI_API_KEY` from the environment or the local
`learning_backend/.env.local` file. If neither is configured, it prompts without
displaying or saving your input. Open **http://127.0.0.1:8010**.
Keep the terminal running; Ctrl+C stops the server.

For persistent local configuration, create `learning_backend/.env.local` with an
`OPENAI_API_KEY=...` entry and restart the server. Git ignores this file, so a fresh
clone needs its own key. An environment variable takes precedence. Python alone
reads the key; it is never sent to the browser or included in generated JSON.
The server binds to `127.0.0.1` for local use.

## Upload-to-study workflow

1. Open a subject from Exam view or Your subjects. Choose **Shallow** or **Deep**
   under Materials, set **Flashcards per PDF** (5–300, default 60), then upload or drop a PDF.
2. The PDF is saved in the browser and submitted to the local Python server.
3. Python uses the chosen mode for both the summary and flashcards, with
   `--sentences 1`, automatic acceptance of the preview, and the chosen number of final cards.
4. A one-sentence summary is saved first. It appears automatically as a read-only
   description under the file title and in the Materials list.
5. Questions and answers are saved to JSON and displayed in the existing flashcard panel.
   The existing reveal, folder practice, and Anki `.apkg` export use these cards.

Generated cards replace previous generated/demo cards. Manually added cards are kept.
Polling reads the JSON again without rerunning the model; reopening the browser reconnects
to saved results. The retry button resumes incomplete work from the pipeline checkpoint.
Completed uploads are idempotent: retrying the same file ID does not generate a duplicate set.
The count is saved per PDF and retained when switching modes or retrying. Changing the
overall count applies to new uploads.

The PDF viewer scrolls through every page continuously; nearby pages render on demand.
Click the **PDF** badge to return from a flashcard without losing your scroll position.
The toolbar keeps only the source badge and download link, and PDF title edits save on blur.
Use the trash button beside a PDF to delete its browser copy, generated cards, and all
server-side results. Deleting an active job stops subsequent model requests and removes
its files when the current request finishes; interrupted cleanup resumes after restart.

**Shallow** extracts readable text only and is faster. **Deep** sends the complete PDF
so the model can read page images, charts, diagrams, and text; it is slower. Use Deep for
scanned PDFs and slides that depend on visuals. You can switch modes in an open PDF's
flashcard panel and click **Generate in deep/shallow mode**. Each mode keeps its own
results and checkpoints, so switching back reuses completed work. Mixed-mode uploads
can run concurrently. Waiting labels animate through `.`, `..`, and `...`; reduced-motion
preferences show static dots.

PDF content is sent to your configured OpenAI API account for generation. Normal API
usage charges apply. Shallow mode reports pages without extractable text instead of
silently skipping them.

## JSON files

Each uploaded file has its own directory, excluded from Git:

```text
learning_backend/data/<file-id>/source.pdf
learning_backend/data/<file-id>/<shallow-or-deep>/result.json
learning_backend/data/<file-id>/<shallow-or-deep>/result.work/<checkpoint>.json
```

The upload sends `X-Learning-Mode: shallow` or `deep` and `X-Flashcard-Count: 60`
(or the chosen count). Deletion uses `DELETE /api/learning/documents/<file-id>`.
The frontend reads
`GET /api/learning/documents/<file-id>/result.json?mode=shallow` (or `deep`).
This serves the saved JSON, including the mode, current status, and original
`documents` collection. Results from the previous folder layout remain readable.

```json
{
  "id": "file-id",
  "mode": "shallow",
  "status": "complete",
  "requested_sentences": 1,
  "documents": [{
    "abstract": "The lecture explains the main concepts of probability.",
    "sentence_count": 1,
    "requested_sentences": 1,
    "questions": [{"question": "What is an event?", "answer": "A set of possible outcomes."}],
    "complete": true
  }]
}
```

This is a schema example, not generated study content. Files may have an abstract while
`status` is still `running`. Errors remain visible with a retry action; results are never
replaced by demo content. JSON remains the storage/API format but is not exposed as a viewer control.

## Development

Run Python from the repo root in one terminal (it also reads the local key file):

```bash
./.venv/Scripts/python.exe -m learning_backend.server
```

Run Angular in a second terminal:

```bash
cd frontend
npm start
```

Angular uses http://127.0.0.1:4300 and proxies `/api/learning/**` to Python on port 8010.
The original frontend can keep running on port 4200. Each origin has separate browser storage.

The defaults preserve the original script's `gpt-6-astra` model and shallow mode.
Optional server environment settings: `OPENAI_MODEL`, `OPENAI_BASE_URL`.
The frontend chooses the mode separately for each PDF; `PDF_DEEP_MODE` only sets the
standalone CLI's default when `--mode` is omitted.
Use `--questions 15` when starting the server to change its fallback count for requests
without a count header; the frontend sends the number entered in Materials.
The summary sentence count is `SUMMARY_SENTENCES = 1` in `learning_backend/server.py`.

The adapted standalone CLI remains available:

```bash
./.venv/Scripts/python.exe learning_backend/pdf_study.py "slides.pdf" --mode deep --sentences 1 --questions 15 --feedback "" --output study_materials.json
```

## Checks

```bash
./.venv/Scripts/python.exe -m unittest learning_backend.test_pipeline -v
cd frontend
npm test
npm run build
```

Automated backend tests use synthetic PDFs and mock only the model response boundary;
they do not call OpenAI or spend credits. They exercise extraction, sentence correction,
JSON/checkpoint writes, uploads, result reads, duplicate requests, concurrent deep/shallow
jobs, textless PDFs, separate mode caches, custom card counts, deletion during generation,
cleanup after restart, and missing-key errors.
Frontend tests cover partial results, real-card mapping, manual-card preservation, and
malformed JSON. A valid server API key is required for a live generation run.

OpenAI response schema reference: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
