"""The study app backend: one Flask app, one blueprint per feature.

- auth/        login, logout, current user
- planner/     the user's semesters and dashboard
- catalog/     the ETH course catalog
- flashcards/  PDF -> flashcards -> Anki deck (engine/ holds the logic)
"""
import os

from flask import Flask, jsonify, send_from_directory

from . import auth, config, db, flashcards, planner


def create_app(overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(config.from_env())
    if overrides:
        app.config.update(overrides)

    db.init_app(app)
    with app.app_context():
        db.init_db()

    auth.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(planner.bp)
    app.register_blueprint(flashcards.bp)

    @app.errorhandler(413)
    def too_large(_exc):
        return jsonify(error="The upload is too large (max. 50 MB PDF)."), 413

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        # Serve built Angular files; fall back to index.html for client-side routes.
        static_dir = app.config["STATIC_DIR"]
        if path and os.path.isfile(os.path.join(static_dir, path)):
            return send_from_directory(static_dir, path)
        return send_from_directory(static_dir, "index.html")

    return app
