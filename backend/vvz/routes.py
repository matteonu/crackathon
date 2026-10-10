"""HTTP endpoints over the local VVZ database. Like every /api route, auth.py has already
checked the caller before these run.

    GET /api/vvz/status                      -> when the data was built, which semesters
    GET /api/vvz/units?q=Analysis&semkez=2026W&section=Computer%20Science%20Bachelor&limit=20
    GET /api/vvz/units/<id>                  -> unit with courses, timeslots, lecturers, sections, rating
    GET /api/vvz/timetable?ids=203292,204074 -> weekly slots of several units (clash detection)
"""

from flask import Blueprint, current_app, jsonify, request

from . import queries

bp = Blueprint("vvz", __name__, url_prefix="/api/vvz")


def _db():
    return current_app.config["VVZ_DB_PATH"]


@bp.errorhandler(queries.NotSynced)
def not_synced(exc):
    return jsonify(error="VVZ data is not synced yet", detail=str(exc)), 503


@bp.get("/status")
def status():
    return jsonify(queries.status(db_path=_db()))


@bp.get("/units")
def units():
    try:
        limit = min(int(request.args.get("limit", 50)), 500)
    except ValueError:
        return jsonify(error="limit must be an integer"), 400
    return jsonify(queries.search_units(
        q=request.args.get("q", ""),
        semkez=request.args.get("semkez"),
        section=request.args.get("section"),
        limit=limit,
        db_path=_db(),
    ))


@bp.get("/units/<int:unit_id>")
def unit(unit_id):
    found = queries.get_unit(unit_id, db_path=_db())
    if found is None:
        return jsonify(error="unit not found"), 404
    return jsonify(found)


@bp.get("/timetable")
def timetable():
    try:
        ids = [int(x) for x in request.args.get("ids", "").split(",") if x.strip()]
    except ValueError:
        return jsonify(error="ids must be comma-separated integers"), 400
    return jsonify(queries.weekly_timetable(ids, db_path=_db()))
