"""HTTP endpoints over the course catalogue. Like every /api route, auth.py has already
checked the caller before these run.

    GET /api/courses?q=Analysis&semkez=2026W&section=Computer%20Science%20Bachelor&limit=20
    GET /api/courses/<id>?semkez=2026W      -> course with the offering of that semester (default: latest)
    GET /api/courses/timetable?ids=5,2&semkez=2026W
    GET /api/courses/sync-status            -> what the VVZ sync last imported
"""

from flask import Blueprint, current_app, jsonify, request

from . import queries

bp = Blueprint("courses", __name__, url_prefix="/api/courses")


def _db():
    return current_app.config["DATABASE_PATH"]


@bp.get("/sync-status")
def sync_status():
    return jsonify(queries.status(db_path=_db()))


@bp.get("")
def search():
    try:
        limit = min(int(request.args.get("limit", 50)), 500)
    except ValueError:
        return jsonify(error="limit must be an integer"), 400
    return jsonify(queries.search_courses(
        q=request.args.get("q", ""),
        semkez=request.args.get("semkez"),
        section=request.args.get("section"),
        limit=limit,
        db_path=_db(),
    ))


@bp.get("/<int:course_id>")
def course(course_id):
    found = queries.get_course(course_id, semkez=request.args.get("semkez"), db_path=_db())
    if found is None:
        return jsonify(error="course not found"), 404
    return jsonify(found)


@bp.get("/timetable")
def timetable():
    semkez = request.args.get("semkez", "")
    if not semkez:
        return jsonify(error="semkez is required, e.g. 2026W"), 400
    try:
        ids = [int(x) for x in request.args.get("ids", "").split(",") if x.strip()]
    except ValueError:
        return jsonify(error="ids must be comma-separated integers"), 400
    return jsonify(queries.weekly_timetable(ids, semkez, db_path=_db()))
