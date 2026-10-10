# crackathon

On the `frontend_plus_learningView` branch, run `bash start-learning.sh` for the subject
learning view with real PDF summaries and flashcards. See [LEARNING_VIEW.md](LEARNING_VIEW.md)
for setup, JSON output, and development commands.

Team repo for the VIScon 2026 Hackathon. Replace `NN` below with our team number.

## Running the app

Flask (`backend/`) serves the API under `/api` and the built Angular app (`frontend/`) for every other path.

**Deploy:** every push to `main` is deployed to the VM by `.github/workflows/deploy.yml`. One-time VM setup:

```bash
cp .env.example .env           # then set SECRET_KEY, e.g. python3 -c "import secrets; print(secrets.token_hex(32))"
docker compose up -d --build   # serves on :8080, restarts automatically
```

**Develop locally:**

```bash
# Terminal 1: backend on :8080
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/python backend/app.py

# Terminal 2: frontend with hot reload on :4200 (proxies /api to :8080)
cd frontend && npm install && npm start
```

**UI components:** the frontend uses [zard/ui](https://zardui.com) with Tailwind. Components are copied into `frontend/src/app/shared/components/`; add more with `cd frontend && npx zard-cli@1.0.1 add <name>` (see the component list on the zard/ui site).

## Data

The database is rebuilt from git on every start, both locally and on the server. Whatever users change in the app is gone after the next restart or deploy, and the only way to change the starting data is a commit.

- **`backend/schema.sql`:** all tables. Add new tables here. Currently: `users`, `courses` (shared catalog) with `course_resources`, each user's `semesters`, the courses taken per semester (`semester_courses`, with `desired_grade`), and `statistics` per user and semester.
- **`backend/seed/NN_<table>.json`:** the starting rows for each table, as a list of `{column: value}` objects. Files load in number order, so a table that others reference needs a lower number. A `password` field is hashed into `password_hash` when loading.

Demo logins: `alice` / `alice123`, `bob` / `bob123` (see `backend/seed/01_users.json`). The repo is public, so these are not secret.

```bash
.venv/bin/flask --app backend/app.py reset-db    # reload the seed without restarting
.venv/bin/flask --app backend/app.py dump-seed   # write the current database back into backend/seed/
```

To build test data by hand, click it together in the app, run `dump-seed`, check the diff, and commit. On the server, `docker compose restart` reloads the seed.

**Login:** there's no sign-up form; accounts come from the seed. Flask-Login keeps the session in a cookie. Protect a new endpoint with `@login_required`, and use `current_user.username` to see who's calling.

## Deadlines

- **Sunday noon:** we lose access to the VM, so the app must already be running on its own (Docker Compose with `restart: unless-stopped`).
- **Before submission:** make this repo public and link it on our team page.

## Infrastructure

- **VM:** Ubuntu 26.04, 4 vCPUs, 8 GB RAM, 80 GB disk. The user is `viscon` with full sudo. Docker, Node.js 24 and Python 3.14 are preinstalled. The SSH config and the password are on the team page.
- **Web app:** serve plain HTTP on `0.0.0.0:8080`. The proxy at `https://NN.hackathon.ethz.ch` handles TLS and login. By default only our team, our mentors and the staff can access it.
- **Direct access:** `NN-direct.viscon-hackathon.ch` is for SSH and any ports we open ourselves (`sudo ufw allow <port>/tcp`).
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
