# Integrated learning view

The subject file viewer is connected to `backend/learning/pdf_study.py`. The pipeline runs
inside the one Flask app (`backend/learning/routes.py` serves it, `jobs.py` runs it), so there
is no second server and no second port.

## Run it

On Windows in Git Bash, use `.venv/Scripts/python.exe` instead of `.venv/bin/python`.

```bash
.venv/bin/python backend/app.py          # :8080, API and the built frontend
cd frontend && npm start                 # :4300 with hot reload, proxies /api to :8080
```

The key comes from `OPENAI_API_KEY` in the repo's `.env` (gitignored, so a fresh clone needs
its own). An environment variable takes precedence. Python alone reads the key; it never
reaches the browser and is never written into generated JSON. The backend prints at startup
whether it found a key, and `GET /api/learning/health` reports it.

## Upload-to-study workflow

1. Open a subject from the Overview or Your subjects. Under **Materials**, open **Upload PDF**
   and choose **Slides**, **Exercises**, **Solutions**, **Exams**, or **Scripts**. The upload
   goes into the selected folder. Dragged PDFs use the last selected document type.
2. Uploading stores the PDF once and automatically starts a **summary-only** job. The
   one-sentence summary uses full PDF pages (deep mode), including scanned pages and visuals.
   It appears under the file title and in the Materials list; no example or final cards
   are generated during this job.
3. Open a Slides, Solutions, or Scripts PDF to generate flashcards. Choose **Shallow** or
   **Deep**, enter **Anki cards** (5–300, default 60), then press **Generate flashcards**.
   The existing summary stays visible and is reused. Exercises, Exams, and legacy PDF
   categories show the source and summary without a flashcard panel.
4. Questions and answers are saved to JSON and displayed in the flashcard panel.
   Reveal, folder practice, and Anki `.apkg` export use these cards. Changing the count
   starts a new run for the same PDF; no new upload is needed.

Generated cards replace previous generated/demo cards. Manually added cards are kept.
Polling reads the JSON again without rerunning the model; reopening the browser reconnects
to saved results. The retry button resumes incomplete work from the pipeline checkpoint.
Completed uploads are idempotent: retrying the same file ID does not generate a duplicate set.
The count is saved per PDF and retained when switching modes or retrying.

The PDF viewer scrolls through every page continuously; nearby pages render on demand.
The surrounding dialog stays within the screen with a short scroll to its remaining
controls. The close button stays visible, and the page behind the dialog does not scroll.
Click the **PDF** badge to return from a flashcard without losing your scroll position.
The toolbar keeps only the source badge and download link, and PDF title edits save on blur.
Use the minus button after a file's status dropdown to delete its row, the stored PDF,
its generated cards and all server-side results. A folder's trash button follows its Anki
export button and asks for confirmation before removing the folder and everything inside.
Stale entries are reconciled with the server when opening or deleting them, or returning
to the window. Read-only Windows files are cleaned up; locked files are queued for cleanup
without leaving a deleted row in the interface.
Deleting an active job stops subsequent model requests and removes
its files when the current request finishes; interrupted cleanup resumes after restart.

**Shallow** extracts readable text only and is faster. **Deep** sends the complete PDF
so the model can read page images, charts, diagrams, and text; it is slower. Use Deep for
scanned PDFs and slides that depend on visuals. You can switch modes in an open PDF's
flashcard panel and click **Generate flashcards**. Each mode keeps its own
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
data/learning/<file-id>/summary/deep/result.json
data/learning/<file-id>/<shallow-or-deep>/result.json
data/learning/<file-id>/<shallow-or-deep>/result.work/<checkpoint>.json
```

`DATA_DIR` sets the root (`data/` locally, `/app/data` in the container, bind-mounted so it
survives a redeploy).

Summary submission sends `X-Learning-Task: summary` with `X-Learning-Mode: deep`.
Explicit card submission sends `X-Learning-Task: flashcards`, the selected
`X-Learning-Mode: shallow` or `deep`, and `X-Flashcard-Count: 60` (or the chosen count).
File and folder deletion uses `DELETE /api/materials/<file-id>`.
The frontend reads
`GET /api/learning/documents/<file-id>/result.json?mode=deep&task=summary` for summaries,
and `?mode=shallow&task=flashcards` (or `deep`) for cards.
This serves the saved JSON, including the task, mode, current status, and original
`documents` collection. Results from the previous folder layout remain readable.

```json
{
  "id": "file-id",
  "mode": "shallow",
  "task": "flashcards",
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
