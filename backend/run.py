"""Local development server.

Rebuilds the database from backend/seed/ once at startup, then runs Flask in
debug mode on :8080. Production uses gunicorn with `studyapp:create_app()`.
"""
import os

from studyapp import create_app, db

app = create_app({"SECRET_KEY": os.environ.get("SECRET_KEY") or "dev-only-secret"})

if __name__ == "__main__":
    # The debug reloader runs this file twice; only reset in the outer process,
    # so code reloads keep the data you clicked together.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        with app.app_context():
            db.reset_db()
    app.run(host="0.0.0.0", port=8080, debug=True)
