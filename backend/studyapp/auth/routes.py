from flask import Blueprint, jsonify, request
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from . import queries

bp = Blueprint("auth", __name__, url_prefix="/api")
login_manager = LoginManager()


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]


@login_manager.user_loader
def load_user(user_id):
    row = queries.get_user_by_id(user_id)
    return User(row) if row else None


@login_manager.unauthorized_handler
def unauthorized():
    # The frontend is a single-page app, so answer with JSON instead of redirecting.
    return jsonify(error="unauthorized"), 401


def init_app(app):
    login_manager.init_app(app)


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    row = queries.get_user_by_username(data.get("username", ""))
    if row is None or not check_password_hash(row["password_hash"], data.get("password", "")):
        return jsonify(error="invalid credentials"), 401
    login_user(User(row))
    return jsonify(username=row["username"])


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return "", 204


@bp.get("/me")
@login_required
def me():
    return jsonify(username=current_user.username)
