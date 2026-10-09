from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from . import queries

bp = Blueprint("planner", __name__, url_prefix="/api")


@bp.get("/dashboard")
@login_required
def dashboard():
    return jsonify(queries.get_dashboard(current_user.id))
