"""Shared test setup: an app whose database and data directory live in a temp folder."""
from pathlib import Path

from app import create_app
import db


def build_app(temp, seed=False, **overrides):
    config = {'SECRET_KEY': 'test-only', 'DATA_DIR': str(temp), 'DATABASE_PATH': str(Path(temp) / 'app.db'),
              'LEARNING_DIR': str(Path(temp) / 'learning'), 'STATIC_DIR': str(temp),
              'DEV_USER': '', 'DEV_USER_NAME': ''}
    config.update(overrides)
    app = create_app(config)
    if seed:
        with app.app_context():
            db.reset_db()
    return app
