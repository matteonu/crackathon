"""Local development server.

Rebuilds the database from backend/seed/ once at startup, then runs Flask in
debug mode on :8080. Production uses gunicorn with `studyapp:create_app()`.

Settings come from the environment and, like on the VM, from the repo's .env
file (variables already set in the shell win).
"""
import os

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


def load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env_file(ENV_FILE)

from studyapp import create_app, db  # noqa: E402  (after .env, so config sees it)

app = create_app({"SECRET_KEY": os.environ.get("SECRET_KEY") or "dev-only-secret"})

if __name__ == "__main__":
    # The debug reloader runs this file twice; only reset in the outer process,
    # so code reloads keep the data you clicked together.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        with app.app_context():
            db.reset_db()
        key = app.config["OPENAI_API_KEY"]
        print(f" * Flashcards: OPENAI_API_KEY {'is set' if key else 'is NOT set (add it to .env)'}, model {app.config['MODEL']}")
    app.run(host="0.0.0.0", port=8080, debug=True)
