# crackathon

Team repo for the VIScon 2026 Hackathon. We are team 13.

## How we work

Two long-lived branches:

- **`main` is what is live.** Every push to it deploys to the VM. It is only ever
  fast-forwarded to `dev`; nothing is committed on it directly.
- **`dev` is where features come together.** Keep it runnable.

Your loop:

```bash
git switch dev && git pull            # start from integration
git switch -c study-state             # short-lived branch, hours not days
# ... work, commit ...
git push -u origin study-state        # then open a PR into dev
```

While others move `dev`, keep your branch current with `git fetch origin && git rebase
origin/dev` (your own branch) or `git merge origin/dev` (one somebody else also works on).
`dev` is protected too, so everything lands through a pull request. The checks -- frontend
tests, `tsc`, build, backend tests -- run on every pull request and on every push to `dev`, so
a PR tells you it is green before you merge. Nobody force-pushes `dev`.

### Releasing to the VM

`main` is protected: it cannot be pushed to, so a release is a pull request from `dev` into
`main`. Open it at
<https://github.com/matteonu/crackathon/compare/main...dev>, merge it, and the merge deploys.

Then watch the Actions run -- it refuses to deploy if the tests fail or if the container does
not come back healthy -- and **open <https://13.hackathon.ethz.ch> yourself**. A health check
does not catch a blank page.

Rolling back:

```bash
git switch dev && git revert <bad-sha> && git push   # then release dev again
```

Reverting on `dev` and releasing keeps the two branches in step. Resetting `main` by hand
needs the ruleset turned off, so it is a last resort.

Merge `dev` into `main` early and often, not once at the deadline: each release is a
rehearsal of the thing that has to work on Sunday. Freeze `main` a couple of hours before
noon and only revert after that. Never `ssh` in and edit files on the VM -- the deploy does
`git reset --hard`, so that work disappears without a trace.

### What keeps a stray commit off main

1. **The deploy refuses it.** The `from-dev` job in `.github/workflows/deploy.yml` fails the
   run unless the commit is on `origin/dev` or holds content identical to a commit there, so
   a fix committed straight onto `main` never reaches the VM. A merge button rewrites commits,
   which is why identical content counts.
2. **A pre-push hook catches the accident locally.** Run this once per clone:

   ```bash
   git config core.hooksPath .githooks
   ```

   It then refuses to push `main` anything whose content was never on `origin/dev`, and
   refuses to delete `main`. `--no-verify` skips it, so it is a seatbelt, not a wall.
3. **The branch ruleset on GitHub** already requires a pull request for `main`, which is why
   a direct push is rejected outright. Worth adding to it, if you have repo admin: *Require
   status checks* (`from-dev` and `check`), so a red run cannot be merged at all, and *Block
   force pushes*.

## Running the app

Flask (`backend/`) serves the API under `/api` and the built Angular app (`frontend/`) for every
other path — one process, one port. The PDF pipeline (lecture PDF → summary → flashcards → Anki
deck) lives in `backend/learning/`; see its [module README](backend/learning/README.md) for how
it works.

**Deploy:** every push to `main` runs the frontend and backend checks, then deploys to the VM
(`.github/workflows/deploy.yml`): `git reset --hard origin/main` and
`docker compose up -d --build --wait`. `--wait` holds until the container's health check
passes, so a broken build fails the job instead of taking the app down quietly. One-time VM
setup:

```bash
cp .env.example .env           # then set SECRET_KEY and OPENAI_API_KEY
docker compose up -d --build   # serves on :8080, restarts automatically
```

**Develop locally:**

```bash
# Terminal 1: backend on :8080
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/python backend/app.py

# Terminal 2: frontend with hot reload on :4300 (proxies /api to :8080)
cd frontend && npm install && npm start
```

Serving the built frontend instead of the dev server: `cd frontend && npm run build`, then open
<http://localhost:8080>.

**Or run it in Docker, in dev mode:**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build   # :8080 as alice@ethz.ch
```

Plain `docker compose up -d --build` is the production setup: it expects the reverse proxy to
say who is calling, and locally there is none, so every `/api` route answers 401 and the file
library, the TODO list and the dashboard show "unauthorized". That is not a bug. Use the dev
override locally (it also loads the demo data and sets `DEV_USER`); see "Who is signed in".

**Checks:**

```bash
cd backend && ../.venv/bin/python -m unittest discover -s tests -t .   # never calls OpenAI
cd frontend && npm test && npm run check && npm run build
```

**Flashcards need a key.** Put `OPENAI_API_KEY=sk-...` in `.env` (gitignored). The backend prints
at startup whether it found one, and `/api/learning/health` reports it too. Without a key the
learning view says the model API key is missing.

## Data

SQLite, at `data/app.db`. The container bind-mounts `./data`, so the database, uploaded PDFs
and generated results all survive `docker compose up -d --build`. The seed is loaded once,
when there is no database file yet — a deploy never discards what users added.

- **`backend/schema.sql`:** all tables. Add new tables here. Currently: `users` (identified by
  email, created on first sight), `materials` (each user's file library), `courses` (shared
  catalog) with `course_resources`, each user's `semesters`, the courses taken per semester
  (`semester_courses`, with `desired_grade`), and `statistics` per user and semester.
- **`backend/seed/NN_<table>.json`:** the starting rows for each table, as a list of
  `{column: value}` objects. Files load in number order, so a table that others reference
  needs a lower number.
- **`backend/seed/`** holds what production starts with: the shared course catalog and no
  users, so every real visitor gets an empty workspace of their own.
- **`backend/seed_demo/`** holds the mock dataset (`alice@ethz.ch` and `bob@ethz.ch` with
  semesters and courses). Dev mode and the tests load it *on top of* `backend/seed/` through
  `SEED_DIRS`; production never loads it.

**Dev mode** is a throwaway database with the demo data in it, rebuilt on every start, with
`DEV_USER` standing in for the proxy:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

It writes `data/demo.db` and cannot touch `data/app.db`. Production is plain
`docker compose up -d --build`.

```bash
cd backend
../.venv/bin/flask --app app reset-db    # discard everything and reload the seed
../.venv/bin/flask --app app dump-seed   # write the current database back into the seed files
```

To build demo data by hand, click it together in the app, run `dump-seed`, check the diff, and
commit. Each table keeps the file it was loaded from; a table that has no file yet is written
into `backend/seed_demo/`.

## Files and materials

A material is a folder, a lecture PDF or a small text note, and belongs to one user and one
subject (`backend/materials.py`, `/api/materials`). The metadata is in SQLite; a PDF's bytes
are written once to `data/learning/<id>/source.pdf`, which is also where the pipeline reads
them, so nothing is stored twice and `POST /api/learning/documents/<id>` needs no body.

Each document also has a validated `type` flag (`slides`, `mock_exam`, `exercise`,
`exercise_solution`, or `script`) separate from its file format. Existing libraries are
migrated in place from their categories at startup. See the [learning pipeline documentation](backend/learning/README.md)
for compatibility rules and the independent fast-summary model configuration.

`outputs` (summary and flashcards) and `processing` (the last run's state) are stored as the
JSON the frontend sends. The server never reads inside them, so the card shape can change
without a migration. Everything else -- names, parents, categories, uniqueness within a
folder -- is validated server-side, and every row is scoped to the caller: another user's id
is a 404, not a peek.

**Tasks.** Each subject has a TODO list (`backend/tasks.py`, `/api/tasks`, table `tasks`),
one row per task with title, notes, due date, done flag and a manual position; new tasks go
to the top, done ones are listed separately and can be cleared per subject. Same rules as
materials: validated server-side and scoped to the caller. The frontend side is
`TaskStore` and `TaskListComponent` in the subject sidebar.

The study plan -- subjects, recorded hours, planned sessions and the generated schedule --
lives on the server too, in `backend/planner.py`; see "Study plan and schedule" below.
`StudyStore` is the in-memory copy the pages read, and nothing is kept in browser storage.

## Who is signed in

There is no login form and no password anywhere in this app. The reverse proxy authenticates
every request and adds `X-User-Id` (the user's email) and `X-User-Name`; `backend/auth.py`
reads them and creates the user row the first time it sees an email. Every path under `/api`
needs an identity (except `/api/health`), so a new endpoint is protected by default — call
`auth.current_user()` for the row and scope your query to its `id`.

Those headers are only trustworthy while the app is reachable through the managed address
alone. **Do not** open port 8080 in ufw, and **do not** set access control to `Disabled` on
the team page: either one lets anyone send the headers themselves.

Locally there is no proxy. `python backend/app.py` stands in as `alice@ethz.ch`; set
`DEV_USER=bob@ethz.ch` in `.env` to be someone else. A real header always wins over it, and
on the VM `DEV_USER` is unset, so a request that bypasses the proxy gets 401.

### Signing out only goes two layers deep

There are three sessions between a visitor and this app:

| Session | Who owns it | Can we end it? |
|---|---|---|
| `_oauth2_proxy` cookie | the hackathon proxy | yes, `/oauth2/sign_out` |
| VSETH Keycloak SSO | `auth.vseth.ethz.ch` | yes, its logout endpoint |
| SWITCH AAI / Shibboleth + the ETH IdP | the university | **no** |

`SIGN_OUT_URL` chains the first two: Keycloak's logout (with
`post_logout_redirect_uri`) into the proxy's `/oauth2/sign_out?rd=`, then back here. Keycloak
has to come first, because oauth2-proxy only redirects to `*.hackathon.ethz.ch`.

**You will be signed straight back in**, because the Shibboleth session is still live and the
whole domain is auth-gated, so there is nowhere to land that does not re-authenticate. That is
not a bug we can fix: `auth.vseth.ethz.ch/Shibboleth.sso/Logout` refuses a `return=` with an
`opensaml::SecurityPolicyException`, and a university SSO session is not ours to end anyway.

So: to use the app as somebody else, **open it in a private window**. If a real sign-out
matters for a demo, ask the organizers whether the proxy can send `prompt=login` instead of
`approval_prompt=force` -- that is their config, and it would force a fresh login for every
team's app. Set `SIGN_OUT_URL` empty in `.env` to hide the button entirely.

## Course catalogue (VVZ)

The `courses` table is the ETH course catalogue. The seed puts a few rows in it; the VVZ sync (`backend/vvz/sync.py`) fills and refreshes it from the database dump of the community project [vvzapi.ch](https://vvzapi.ch) ([markbeep/vvzapi](https://github.com/markbeep/vvzapi), GPLv3; we use its data, not its code, and credit it here). Every course gets ECTS, exam mode, the Basisprüfung block, lecturers, programme sections and student ratings, and per semester an offering with the lecture/exercise parts, their weekly hours and room timeslots.

- **Schema:** in `backend/schema.sql`. `courses` is upserted by `code`, so ids survive and `semester_courses` keeps pointing at the right rows; `course_offerings` (one per course and semester, id = VVZ lerneinheitId) with `course_lectures`, `course_timeslots`, `course_lecturers`/`lecturers`, `course_sections`, plus `course_ratings` and `vvz_meta`.
- **Which semesters:** previous, current and the next two by default; override with `VVZ_SEMESTERS=2025W,2026S`.
- **When it runs:** nobody triggers it by hand. Every app start (so every deploy and every restart) launches a background thread that syncs about ten seconds after boot and then every 24 h (`VVZ_REFRESH_SECONDS`); `VVZ_AUTO_SYNC=0` turns that off. A sync asks vvzapi.ch whether the dump changed, downloads it only then, and imports only when the database does not already hold that dump for these semesters, so a redeploy with up-to-date data is a no-op. The import is one transaction, so requests see either the old or the new catalogue. To force one: `docker compose exec app python -m vvz.sync --force`.
- **Cache:** the downloaded dump is cached as `data/vvz-dump.zip`, which is how `reset-db` and `wipe` refill the catalogue in a second without the network, and how a sync still imports when vvzapi.ch is down. A fresh deployment with an empty `data/` downloads it on first start (about 70 MB, ten seconds); until then the catalogue holds only the seed.
- **On the VM:** `data/` is a bind mount, so the database and the cache survive `docker compose up --build`. The GitHub Actions deploy (`.github/workflows/deploy.yml`) runs the backend tests, which never touch the network, then restarts the container; the sync thread then does its start-up check as described above.
- **dump-seed** skips the synced tables and writes only the courses the demo data references, so the seed files stay small.
- **Known gap:** upstream has no timeslots for autumn 2026 yet, although VVZ itself lists them. An offering without slots gets the slots of the same course one year earlier, marked with `inherited_from`, so treat those as "probably" and show the flag in the UI.

```bash
cd backend
../.venv/bin/python -m vvz.sync                   # download the dump (~70 MB) if it changed, then import
../.venv/bin/python -m vvz.sync --force           # import again even if nothing changed
../.venv/bin/python -m vvz.sync --offline         # import from the cached dump, no network
../.venv/bin/python -m unittest tests.test_vvz tests.test_vvz_app
```

No endpoints yet: read the tables directly (`courses`, `course_offerings`, `course_lectures`, `course_timeslots`, ...) from whatever backend code needs them.

## Study plan and schedule

A semester holds the courses you take, what you recorded, what you planned yourself, and a
generated schedule. `backend/planner.py` owns the endpoints, `backend/schedule_planner/` the
algorithm.

- **The scheduler** (`backend/schedule_planner/`) is plain Python: a JSON request in, a
  week-by-week plan out, no Flask, no database, no clock. It fills each day with blocks of
  `studyBlockSize` minutes around fixed meals, groups a subject's learning blocks together,
  and ends each day with one short recall block per subject studied. Hours go where the exam
  is closest and the remaining workload (`30 x ECTS` minus lectures attended minus hours
  already planned) is largest, tilted by difficulty against priority. Try it by hand:

  ```bash
  cd backend
  ../.venv/bin/python -m schedule_planner.main < tests/example_input.json
  ```

- **Generating** is `POST /api/semesters/<semkez>/plan/generate`. `dryRun: true` returns a
  proposal without storing it, which is what the preview dialog shows. `fromDate` is the first
  day to plan and defaults to today clamped into the study phase: blocks before it are kept
  and fed back to the scheduler as history, so pressing the button again next week does not
  rewrite the weeks already behind, and the hours they used still count against a course's cap.
- **Reading** is `GET /api/semesters/<semkez>/plan`, which carries the subjects, your own
  sessions, the habits the plan was built from, and `plan: null` until one has been generated.
  Its totals are added up from the stored blocks, not from the last run, because earlier weeks
  outlive the run that made them.
- **Storage:** `study_plans` holds one row per semester (the run, and the request that produced
  it, so a plan can be reproduced), `plan_blocks` one row per block with its type
  (`active_learning`, `recall`, `meal`). A meal block has no course, which the composite
  foreign key tolerates because SQLite does not enforce one when a column is NULL -- so
  deleting a course still takes its blocks with it. Generated blocks are kept apart from
  `study_sessions`, which is yours: regenerating never touches what you typed.
- **Preferences** are split in two. How a day is laid out belongs to the semester
  (`day_start`, `day_end`, meals, `study_block_size`, `study_hours_per_week`, `alpha`, `beta`)
  and is saved with `PUT /api/semesters/<semkez>/preferences`, along with `semester_days_off`.
  What the scheduler needs per course (`priority`, `difficulty`, `max_study_hours`,
  `lecture_per_week`) goes on `semester_courses` and is saved with the existing
  `PATCH .../courses/<id>`. Every column has a default, so a semester can be planned the
  moment you add a course -- the form only refines it.
- **Where the numbers come from:** ECTS and weekly contact hours from the VVZ offering,
  difficulty from the scraped `course_ratings` rounded to 1-5, and the rest from you. Exam
  dates are not in the VVZ, so they default to the end of the study phase until you set them.
  A course marked finished is left out of the plan.
- **`study_hours_per_week` is the brake.** Left empty, the scheduler fills every free slot
  before your exams, which for a winter phase of 56 days at 08:00-20:00 is around 500 hours.
  Set it and each week stops at that many hours, pro-rated over a part week. Recall blocks are
  placed either way, so a tight week can end a little above the budget -- the same exemption
  `max_study_hours` has.
- **The study phase itself** is fixed per semester in `planner.phase()`: HS runs 21 Dec to
  14 Feb, FS 1 Jun to 31 Aug. It is not user-settable yet; the VVZ API would be the place to
  get the real session dates from.

```bash
cd backend && ../.venv/bin/python -m unittest tests.test_schedule tests.test_schedule_api
```

## Deadlines

- **Sunday noon:** we lose access to the VM, so the app must already be running on its own (Docker Compose with `restart: unless-stopped`).
- **Before submission:** make this repo public and link it on our team page.

## Infrastructure

- **VM:** Ubuntu 26.04, 4 vCPUs, 8 GB RAM, 80 GB disk. The user is `viscon` with full sudo. Docker, Node.js 24 and Python 3.14 are preinstalled. The SSH config and the password are on the team page.
- **Web app:** serve plain HTTP on `0.0.0.0:8080`. The proxy at `https://13.hackathon.ethz.ch` handles TLS and login. By default only our team, our mentors and the staff can access it.
- **Direct access:** `13-direct.viscon-hackathon.ch` is for SSH and any ports we open ourselves (`sudo ufw allow <port>/tcp`). Don't open 8080: that is what makes the user headers trustworthy.
- **Auth for free:** the proxy sends `X-User-Id` (the user's email) and `X-User-Name` with every request. These are only trustworthy while the app is reachable solely through the managed address.
- **No WebSockets.** Use Server-Sent Events or Socket.IO instead.
- **Template:** a React and FastAPI example app is running in `~/template`. Redeploy it with `docker compose up -d --build`, or remove it with `docker compose down`.
- **Dev tip:** use VS Code Remote-SSH, and forward ports with `ssh -L 5173:localhost:5173 viscon-2026`.

## AI

Any AI tools are allowed.

- **OpenAI:** each participant gets $100 in credits. The promo code is under "My Secrets" on the hackathon site.
- **Team LiteLLM key:** $5 per team, on the OpenAI-compatible proxy at `https://llm.hackathon.ethz.ch`. The default model is `openrouter/deepseek/deepseek-v4.1-flash`.
- Call LLMs from the backend only, and never commit keys.

## Rules

- Don't misuse the VMs or the network, and don't interfere with other teams.
- Never touch anything marked "VIScon Admin", including firewall rules.
- When stuck on anything, ask the organizers (in person or on Discord) or our mentor.

## Scoring (max 90)

| Component | Points |
|---|---|
| Technical (internal questionnaire) | 20 |
| Product (70% product, 30% presentation) | 30 |
| Sidequests | 10 |
| Public vote (finalists only) | 30 |

Each component is normalized against the best team's score.

- **Nomination round (Sunday):** we present to our stakeholder group. The best team in each group goes straight to the final. The second-best is nominated, and the jury picks 2–5 finalists from the nominees.
- **Final:** the finalists present to everyone, and participants vote for their top 3 teams (5, 3 and 1 points).
- **Sidequests:** you can do one per hour, at the helpdesk. They are ranked per leaderboard, and the team score is the average over members, so everyone should try every sidequest.
