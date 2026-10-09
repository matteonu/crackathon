"""All settings, read from the environment when the app is created."""
import os

from .db import BACKEND_DIR


def from_env():
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", os.path.join(BACKEND_DIR, "data", "app.db")),
        "STATIC_DIR": os.environ.get(
            "STATIC_DIR", os.path.join(BACKEND_DIR, "..", "frontend", "dist", "frontend", "browser")
        ),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        # Flashcard uploads are PDFs of up to 50 MB sent as base64 JSON (about 4/3 larger).
        "MAX_CONTENT_LENGTH": 70 * 1024 * 1024,
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "").strip(),
        "MODEL": os.environ.get("MODEL", "gpt-5-mini"),
        "OPENAI_ENDPOINT": os.environ.get("OPENAI_ENDPOINT", "https://api.openai.com/v1/responses"),
    }
