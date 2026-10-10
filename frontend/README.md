# Studyphase — Angular frontend

A working Angular version of the Figma dashboard kit and the original hackathon skeleton. It preserves the Full schedule, What’s next, Analytics, and Modify schedule structure, with a sage sidebar, subject colours, and spreadsheet-style data.

## Run locally

Use Node.js 24.15 or later in the Node 24 series (the project was built with Node 24.19), or Node 22.22.3+.

```bash
npm ci
npm start
```

Open http://127.0.0.1:4300. The Flask backend runs on port 8080; this development server proxies `/api` to it. See [LEARNING_VIEW.md](../LEARNING_VIEW.md) for backend startup and API-key setup.

```bash
npm test       # data, dates, totals, and import validation
npm run check # TypeScript check
npm run build # production Angular build, including strict template checking
```

The production files are written directly to `dist/` and served by the Python learning server. Hash-based routes keep navigation and refresh working without server rewrite rules.

## What works

- Overview: Full schedule and What’s next span the main area; Analytics sits beside Modify schedule, as in the skeleton.
- Full detail opens Schedule, where Calendar and Hours overview share the selected week. Close or Escape in Hours overview returns to the overview.
- Horizontal scrolling: each schedule, exam table, and analytics panel has native scrolling, a scrollbar, and left/right buttons. Subject labels stay visible in the schedule. Arrow keys work when the scroll region has focus; trackpad and touch scrolling are native.
- Weekly navigation covers the complete December 2024–February 2025 study phase, including partial weeks at its edges.
- Select any date/subject cell to edit its recorded hours. The modal uses a native dialog for focus containment, Escape dismissal, and focus return.
- Totals, hours remaining, subject progress, and weekly summaries recalculate immediately.
- Exam view supports All, Still to do, and Completed filters. Click a status to change it.
- Subject pages let you edit a target, exam date, next action, and completion status.
- PDF uploads generate a one-sentence summary from Python JSON. Choose Slides, Exercises, Solutions, Exams, or Scripts in the upload dropdown. Slides, Solutions, and Scripts offer optional flashcards: open the PDF, choose Shallow or Deep and 5–300 cards, then click Generate flashcards.
- Generation labels animate through one, two, and three dots, respecting reduced-motion preferences.
- Changes persist in this browser’s local storage. Data & settings includes JSON export/import and restoring the original sample after confirmation.
- Responsive layout for desktop and mobile. Dense tables scroll inside their panels.

## Modify the frontend

| What to change | File |
| --- | --- |
| Colours, typography, spacing, breakpoints, animation | `src/styles.css` |
| Sidebar and page shell | `src/app/app.component.html` |
| Overview arrangement | `src/app/pages/overview.component.ts` |
| Schedule markup and behaviour | `src/app/components/schedule.component.html` and `.ts` |
| Exam list | `src/app/components/next.component.ts` |
| Analytics and Anki display | `src/app/components/analytics.component.ts` |
| Editable subject form | `src/app/pages/subject.component.ts` |
| Original data | `src/app/data/study-data.json` |
| State, persistence, and mutation methods | `src/app/services/study-store.ts` |
| Types, date arithmetic, aggregation, import validation | `src/app/models/study.ts` |
| Routes | `src/app/app.routes.ts` |

When you edit the seed JSON, existing browser data takes precedence. Use **Data & settings → Restore original sample** to load your changed seed, or clear the `studyphase-angular-v1` localStorage key.

## Data and scope

The seed uses the supplied HS24 workbook and Figma kit: five subjects, 58 dates, 353 recorded hours against a 320-hour target. The initial week is 6–12 January 2025 with 57 recorded hours. All five exam statuses are preserved as completed because the workbook is an archive. Anki counts are a static snapshot.

A blank cell means **unrecorded**, not an observed zero. `Hours left = target − recorded`, so negative values mean above target. The overall target can be exceeded while an individual subject still has hours remaining. A day’s combined hours cannot exceed 24. Save in the hour editor **replaces** that subject/day value; it does not increment it.

Study data and a local copy of uploaded PDFs stay in browser storage. PDF uploads are also sent to the local Python server, which generates a one-sentence summary and flashcards with OpenAI and saves JSON results. Suggestions and schedule proposals still use labeled demo adapters. No cross-device sync or live Anki connection is implemented. Planned calendar sessions are separate from recorded daily totals.

`LearningPipelineService` uploads PDFs and polls the saved result JSON; `MaterialStore` merges the generated summary and cards while preserving manual cards. `PlannedSession` separates subject, date, start time, and duration from recorded hours.

## Validation

Angular production compilation and strict template checking pass. Automated tests cover imported totals, weekly totals, updates, blank versus zero, date boundaries, metadata, planned sessions, and invalid imports. Browser interaction checks cover the Subject and Schedule workflows; see the update notes below.

## Framework references

- [Angular version compatibility](https://angular.dev/reference/versions)
- [Angular signals](https://angular.dev/guide/signals)
- [Router view transitions](https://angular.dev/guide/routing/route-transition-animations)

Angular and Angular CLI are pinned to 22.2.2, with TypeScript 6.0.3. Icons are inline SVG; no third-party charting library, image service, or external font request is required.

## Subject and Schedule workspaces

- Subject: a browser-local PDF library (multiple PDFs, up to 50 MB each), To read / Done / Revisit / Ignore markers, search, continuous scrolling in the local PDF.js preview, and download. PDFs and generated results persist in IndexedDB, separately from JSON export/import and sample reset. Trash buttons delete PDFs and their saved results from both the browser and the local Python server.
- Uploaded PDFs automatically use the real Python pipeline for summaries and flashcards. The generated summary is read-only; processing status and retry errors are shown in the file viewer.
- Metadata includes ECTS, lecture ID, homepage, target hours, and exam date. Suggestions can be edited and accepted. Subject Anki analytics use explicitly linked snapshot decks; no live Anki service is connected.
- Schedule (`#/schedule`, with `#/study-view` redirecting) toggles between a weekly calendar and recorded-hour overview. Planned sessions can be added, edited, and deleted; overlapping sessions are rejected. A demo proposal is previewed before it is applied. The bottom legend totals planned hours for the displayed week.
- Plans persist as `sessions` in exported study data and never contribute to recorded hours. `examSession` supplies explicit inclusive recording bounds; older exports fall back to the saved study-phase date range.
- Recording uses individual DD / MM / YYYY inputs. Reactive form controls load the current cell synchronously before focus; invalid or out-of-session dates cannot be saved.
- PDF.js and its worker, character maps, standard fonts, and codecs are served locally. No PDF is sent to a remote viewer.

Validation for the first workspace update: 12 model tests cover date parsing, session boundaries, overlaps, persistence shape, unchanged recorded totals, and safe metadata. Browser checks cover switching hour cells, date rejection, calendar proposals, PDF upload and markers, and demo generation. The test PDF in `tests/fixtures/` contains synthetic material only.

## Materials explorer and file viewer

- Materials is each subject’s root. Each folder row offers **New folder** and **Upload PDF** icons immediately before **View all flashcards**; these actions create or upload directly into that folder. Folders expand independently, and search preserves matching files’ ancestors. Existing PDFs migrate to the root without losing their markers or demo results.
- Click a file to open its viewer. PDF descriptions are generated automatically as one sentence. PDF titles save when the input loses focus; existing text and Markdown files also support local content and description edits. The viewer toolbar contains the source badge and **Download file**, with no folder/status dropdowns or JSON link.
- The left pane shows every PDF page in a scrollable document; the right pane lists saved flashcards. Selecting a card replaces the source with a question and revealable answer. Click outside the card, press Escape, or use the **PDF** badge to restore the source without resetting its scroll position. Pages render near the viewport to limit canvas memory.
- Generation loads question/answer pairs from the Python result JSON and replaces old generated/demo cards. You can also write your own cards, which are preserved. File content, metadata, folders, and cards persist in IndexedDB in this browser; Python results and checkpoints are also saved under `learning_backend/data/`. They remain separate from the study-data JSON export.
- Every folder, including Materials, offers **View all cards**, **Start learning**, and **Export .apkg**. Folder collections include all nested files. Practice supports reveal, review again, got it, and completion; review progress lasts for that practice session.
- Anki `.apkg` export runs entirely in the browser using lazily loaded SQL.js and fflate. It writes a SQLite `collection.anki2` and empty media manifest into a ZIP package. The package includes text cards only; demo cards carry a `demo` tag. Stable note IDs avoid creating new identities on repeated exports. Format reference: [genanki’s package implementation](https://github.com/kerrickstaley/genanki/tree/main/genanki). No backend or Anki connection is used.
- New implementation: `models/material.ts`, `services/material-store.ts`, `components/material-library.component.*`, `components/file-viewer.component.*`, `components/folder-flashcards.component.ts`, and `services/flashcard-export.service.ts`. Package serialization lives in `models/apkg.ts`.
- Validation: 17 tests cover the existing study data plus legacy file migration, nested aggregation, filtering, folder boundaries, and ZIP/SQLite package integrity. Browser checks cover folder and note creation, title/content edits, PDF upload, source/card switching, practice completion, export, persistence, and mobile layouts. Anki desktop import was not tested here.
