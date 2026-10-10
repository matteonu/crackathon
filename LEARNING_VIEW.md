# Integrated learning view

The subject file viewer is connected to `backend/learning/pdf_study.py`. The pipeline runs
inside the one Flask app (`backend/learning/routes.py` serves it, `jobs.py` runs it), so there
is no second server and no second port.

## Run it

```bash
.venv/bin/python backend/app.py          # :8080, API and the built frontend
cd frontend && npm start                 # :4300 with hot reload, proxies /api to :8080
```

The key comes from `OPENAI_API_KEY` in the repo's `.env` (gitignored, so a fresh clone needs
its own). An environment variable takes precedence. Python alone reads the key; it never
reaches the browser and is never written into generated JSON. The backend prints at startup
whether it found a key, and `GET /api/learning/health` reports it.

## Upload-to-study workflow

1. Open a subject from Exam view or Your subjects. Choose **Shallow** or **Deep**
   under Materials, set **Flashcards per PDF** (5–300, default 60), then upload or drop a PDF.
2. The PDF is saved in the browser and submitted to the backend.
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
data/learning/<file-id>/source.pdf
data/learning/<file-id>/<shallow-or-deep>/result.json
data/learning/<file-id>/<shallow-or-deep>/result.work/<checkpoint>.json
```

`DATA_DIR` sets the root (`data/` locally, `/app/data` in the container, bind-mounted so it
survives a redeploy).

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

Angular serves on http://127.0.0.1:4300 and proxies `/api` to Flask on :8080. Browser storage
is per origin, so the dev server and the built app on :8080 keep separate material libraries.

The defaults preserve the original script's `gpt-6-astra` model and shallow mode.
Optional server environment settings: `OPENAI_MODEL`, `OPENAI_BASE_URL`.
The frontend chooses the mode separately for each PDF; `PDF_DEEP_MODE` only sets the
standalone CLI's default when `--mode` is omitted.
`DEFAULT_QUESTIONS` in `backend/learning/jobs.py` is the fallback count for a request without
a count header; the frontend sends the number entered in Materials. The summary sentence count
is `SUMMARY_SENTENCES` in the same file.

The adapted standalone CLI remains available:

```bash
.venv/bin/python backend/learning/pdf_study.py "slides.pdf" --mode deep --sentences 1 --questions 15 --feedback "" --output study_materials.json
```

## Checks

```bash
cd backend && ../.venv/bin/python -m unittest discover -s tests -t . -v
cd frontend && npm test && npm run check && npm run build
```

Automated backend tests use synthetic PDFs and mock only the model response boundary;
they do not call OpenAI or spend credits. They exercise extraction, sentence correction,
JSON/checkpoint writes, uploads, result reads, duplicate requests, concurrent deep/shallow
jobs, textless PDFs, separate mode caches, custom card counts, deletion during generation,
cleanup after restart, and missing-key errors.
Frontend tests cover partial results, real-card mapping, manual-card preservation, and
malformed JSON. A valid server API key is required for a live generation run.

OpenAI response schema reference: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
