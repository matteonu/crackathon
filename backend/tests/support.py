"""Shared test setup: an app whose database and data directory live in a temp folder."""
import os
from pathlib import Path

from app import BACKEND_DIR, create_app
import db


def build_app(temp, seed=False, **overrides):
    config = {'SECRET_KEY': 'test-only', 'DATA_DIR': str(temp), 'DATABASE_PATH': str(Path(temp) / 'app.db'),
              'LEARNING_DIR': str(Path(temp) / 'learning'), 'STATIC_DIR': str(temp),
              'SEED_DIRS': [os.path.join(BACKEND_DIR, 'seed'), os.path.join(BACKEND_DIR, 'seed_demo')],
              'RESET_DB_ON_START': False, 'SEED_IF_NEW': False, 'DEV_USER': '', 'DEV_USER_NAME': '',
              'VVZ_AUTO_SYNC': False, 'CHAT_BACKGROUND_TASKS': False}
    config.update(overrides)
    app = create_app(config)
    if seed:
        with app.app_context():
            db.reset_db()
    return app
