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
PRs for anything touching shared files -- `backend/app.py`, `backend/schema.sql`,
`frontend/src/app/services/` -- and a direct push to `dev` is fine for your own new files.
Nobody force-pushes `dev`.

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
deck) lives in `backend/learning/`; see [LEARNING_VIEW.md](LEARNING_VIEW.md) for how it works.

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

`outputs` (summary and flashcards) and `processing` (the last run's state) are stored as the
JSON the frontend sends. The server never reads inside them, so the card shape can change
without a migration. Everything else -- names, parents, categories, uniqueness within a
folder -- is validated server-side, and every row is scoped to the caller: another user's id
is a 404, not a peek.

The study plan itself (subjects, hours, sessions) is still kept in the browser by
`StudyStore`. Moving it to the server is the next step, and the shape to aim for is in
CLAUDE.md.

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

**Signing out** is the login provider's job, so the server hands the frontend a URL and the
sidebar shows the button only for a request that came through the proxy. The default chain is
VSETH's Keycloak logout (which ends the single-sign-on session) redirecting to the proxy's
`/oauth2/sign_out` (which clears its cookie) and back to us, where the browser is asked to log
in again. Keycloak has to come first: oauth2-proxy only redirects to `*.hackathon.ethz.ch`.
Override it with `SIGN_OUT_URL` in `.env`, or set it empty to hide the button.

## Course catalogue (VVZ)

`backend/data/vvz.db` is a local copy of the ETH course catalogue: every unit (course) with ECTS, exam mode, Basisprüfung block, lecturers, programme sections, student ratings, and per lecture/exercise the weekly hours and timeslots with rooms. It is **not** part of the seed; it is built by `backend/vvz/sync.py` from the database dump of the community project [vvzapi.ch](https://vvzapi.ch) ([markbeep/vvzapi](https://github.com/markbeep/vvzapi), GPLv3; we use its data, not its code, and credit it here).

- **Schema:** `backend/vvz/schema.sql` (tables `vvz_units`, `vvz_courses`, `vvz_timeslots`, `vvz_lecturers`, `vvz_unit_lecturers`, `vvz_unit_sections`, `vvz_ratings`, `vvz_meta`).
- **Which semesters:** previous, current and the next two by default; override with `VVZ_SEMESTERS=2025W,2026S`.
- **Refresh:** the app starts a background thread that builds the file at start and rebuilds it every 24 h (`VVZ_REFRESH_SECONDS`) when the upstream dump changed; `VVZ_AUTO_SYNC=0` turns that off. The build swaps the file in atomically, so the app never reads a half-built database. Until the first build is done, `/api/vvz/*` answers 503. The file lives in `data/` next to `app.db`, so it survives a redeploy.
- **Known gap:** upstream has no timeslots for autumn 2026 yet, although VVZ itself lists them. For a unit without slots the sync copies the slots of the same unit one year earlier and marks them with `inherited_from`, so treat those as "probably" and show the flag in the UI.

```bash
.venv/bin/python -m vvz.sync                      # download the dump (~70 MB) and build data/vvz.db, run from backend/
.venv/bin/python -m vvz.sync --force              # rebuild even if the dump is unchanged
.venv/bin/python -m vvz.sync --dump database.db   # build from an already downloaded dump
.venv/bin/python -m unittest tests.test_vvz       # tests run against a tiny fake dump, no network
```

Endpoints (need the proxy user like every `/api` route): `GET /api/vvz/status`, `GET /api/vvz/units?q=Analysis&semkez=2026W&section=Computer%20Science%20Bachelor`, `GET /api/vvz/units/<id>`, `GET /api/vvz/timetable?ids=1,2,3`. Python side: `vvz.queries.search_units`, `get_unit`, `weekly_timetable`.

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
