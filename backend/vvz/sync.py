"""Build a local SQLite copy of the ETH course catalogue (VVZ).

The data comes from the community project vvzapi.ch (https://github.com/markbeep/vvzapi),
which scrapes vvz.ethz.ch and publishes a full database dump. We download that
dump, keep only the semesters we care about, and write them into our own, much
smaller schema (see schema.sql). The result is `data/vvz.db`, next to app.db.

Usage:
    python -m vvz.sync                 # sync once, skips if the dump is unchanged
    python -m vvz.sync --force         # rebuild even if the dump is unchanged
    python -m vvz.sync --loop          # sync now, then every VVZ_REFRESH_SECONDS (default: daily)
    python -m vvz.sync --dump path.db  # build from a local dump instead of downloading
    python -m vvz.sync --semesters 2025W,2026S

Environment:
    VVZ_DB_PATH          where to write the database (default: $DATA_DIR/vvz.db, i.e. backend/data/vvz.db)
    VVZ_SEMESTERS        comma-separated semkez list; default: previous, current and next two semesters
    VVZ_API_BASE         default https://vvzapi.ch
    VVZ_REFRESH_SECONDS  loop interval, default 86400
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

log = logging.getLogger("vvz.sync")

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("VVZ_DB_PATH") or os.path.join(os.environ.get("DATA_DIR") or os.path.join(BACKEND_DIR, "data"), "vvz.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
API_BASE = os.environ.get("VVZ_API_BASE", "https://vvzapi.ch").rstrip("/")
REFRESH_SECONDS = int(os.environ.get("VVZ_REFRESH_SECONDS", "86400"))
RETRY_SECONDS = 1800
USER_AGENT = "crackathon-vvz-sync (+https://github.com/matteonu/crackathon)"

COURSE_TYPE_NAMES = {
    "V": "lecture",
    "G": "lecture with exercise",
    "U": "exercise",
    "S": "seminar",
    "K": "colloquium",
    "P": "practical/laboratory course",
    "A": "independent project",
    "D": "diploma thesis",
    "R": "revision course / private study",
}


# ---------------------------------------------------------------- semesters


def semester_of(date: dt.date) -> str:
    """ETH semester key for a date: autumn (W) runs Sep-Jan, spring (S) Feb-Aug."""
    if 2 <= date.month <= 8:
        return f"{date.year}S"
    return f"{date.year - 1}W" if date.month == 1 else f"{date.year}W"


def shift_semester(semkez: str, steps: int) -> str:
    year, term = int(semkez[:4]), semkez[4]
    index = year * 2 + (1 if term == "W" else 0) + steps
    return f"{index // 2}{'W' if index % 2 else 'S'}"


def default_semesters(today: dt.date | None = None, before: int = 1, after: int = 2) -> list[str]:
    current = semester_of(today or dt.date.today())
    return [shift_semester(current, i) for i in range(-before, after + 1)]


def configured_semesters(arg: str | None = None) -> list[str]:
    raw = arg or os.environ.get("VVZ_SEMESTERS", "")
    if raw.strip():
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return default_semesters()


# ---------------------------------------------------------------- download


def fetch_metadata() -> dict:
    req = urllib.request.Request(f"{API_BASE}/api/v2/dump/metadata", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def download_dump(dest_dir: str) -> str:
    """Download and unzip the dump; return the path of the SQLite file inside."""
    zip_path = os.path.join(dest_dir, "dump.zip")
    req = urllib.request.Request(f"{API_BASE}/api/v2/dump", headers={"User-Agent": USER_AGENT})
    log.info("Downloading %s/api/v2/dump", API_BASE)
    with urllib.request.urlopen(req, timeout=600) as resp, open(zip_path, "wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        if not members:
            raise RuntimeError("The dump zip is empty")
        zf.extract(members[0], dest_dir)
        return os.path.join(dest_dir, members[0])


# ---------------------------------------------------------------- build


def _json_list(value) -> str:
    """Normalise a JSON column from the dump to a JSON list string."""
    if value is None:
        return "[]"
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return "[]"
    if parsed is None:
        return "[]"
    return json.dumps(parsed if isinstance(parsed, list) else [parsed], ensure_ascii=False)


def _slot_rows(unit_id: int, course_number: str, semkez: str, timeslots_json, inherited_from: str | None = None) -> list[tuple]:
    rows = []
    for s in json.loads(_json_list(timeslots_json)):
        if not isinstance(s, dict):
            continue
        rows.append((
            unit_id, course_number, semkez, s.get("weekday"), s.get("date"),
            s.get("start_time"), s.get("end_time"), s.get("building"), s.get("floor"), s.get("room"),
            int(bool(s.get("first_half_semester"))), int(bool(s.get("second_half_semester"))),
            int(bool(s.get("biweekly"))), inherited_from,
        ))
    return rows


def _prefer_english(row, column: str):
    return row[f"{column}_english"] or row[column]


def build_db(source_path: str, dest_path: str, semesters: list[str], meta: dict | None = None) -> dict:
    """Copy the given semesters from a vvzapi dump into a fresh database at dest_path.

    Writes to a temporary file first and swaps it in atomically, so a reader never
    sees a half-built database. Returns row counts.
    """
    if not semesters:
        raise ValueError("No semesters selected")
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    tmp_path = dest_path + ".building"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    src = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(tmp_path)
    try:
        with open(SCHEMA_PATH) as f:
            dst.executescript(f.read())
        marks = ",".join("?" for _ in semesters)
        counts = {}

        units = src.execute(f"SELECT * FROM learningunit WHERE semkez IN ({marks}) AND number IS NOT NULL", semesters).fetchall()
        unit_ids = [u["id"] for u in units]
        dst.executemany(
            """INSERT INTO vvz_units (id, semkez, number, title, title_english, credits, levels, departments,
                   language, exam_mode, exam_type, exam_block, course_frequency, max_places, abstract,
                   objective, content, lecture_notes, literature, written_aids)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    u["id"], u["semkez"], u["number"], u["title"], u["title_english"], u["credits"],
                    _json_list(u["levels"]), _json_list(u["departments"]), u["language"], u["exam_mode"],
                    u["exam_type"], _json_list(u["exam_block"]), u["course_frequency"], u["max_places"],
                    _prefer_english(u, "abstract"), _prefer_english(u, "objective"), _prefer_english(u, "content"),
                    _prefer_english(u, "lecture_notes"), _prefer_english(u, "literature"), u["written_aids"],
                )
                for u in units
            ],
        )
        counts["units"] = len(units)

        courses = src.execute(f"SELECT * FROM course WHERE semkez IN ({marks})", semesters).fetchall()
        known = set(unit_ids)
        course_rows, slot_rows = [], []
        units_with_slots = set()
        for c in courses:
            if c["unit_id"] not in known:
                continue
            course_rows.append((
                c["number"], c["semkez"], c["unit_id"], c["title"], c["type"],
                COURSE_TYPE_NAMES.get(c["type"] or "", c["type"]), c["hours"], c["hour_type"], c["comment"],
            ))
            rows = _slot_rows(c["unit_id"], c["number"], c["semkez"], c["timeslots"])
            if rows:
                units_with_slots.add(c["unit_id"])
            slot_rows += rows
        dst.executemany(
            "INSERT OR IGNORE INTO vvz_courses (number, semkez, unit_id, title, type, type_name, hours, hour_type, comment) VALUES (?,?,?,?,?,?,?,?,?)",
            course_rows,
        )
        counts["courses"], counts["timeslots"] = len(course_rows), len(slot_rows)

        # Fallback: vvzapi sometimes has no timeslots yet for a semester (e.g. all of 2026W at the
        # time of writing). ETH timetables are stable year to year, so for a unit without any slot
        # we copy the slots of the same unit number one year earlier and mark them as inherited.
        inherited = 0
        for u in units:
            if u["id"] in units_with_slots:
                continue
            previous = shift_semester(u["semkez"], -2)
            for c in src.execute(
                "SELECT c.* FROM course c JOIN learningunit l ON l.id = c.unit_id WHERE l.number = ? AND c.semkez = ?",
                (u["number"], previous),
            ):
                same_course = c["number"].rsplit(" ", 1)
                course_number = c["number"] if len(same_course) < 2 else f"{u['number'][:-1]} {same_course[1]}"
                rows = _slot_rows(u["id"], course_number, u["semkez"], c["timeslots"], inherited_from=previous)
                slot_rows += rows
                inherited += len(rows)
        counts["inherited_timeslots"] = inherited
        dst.executemany(
            """INSERT INTO vvz_timeslots (unit_id, course_number, semkez, weekday, date, start_time, end_time,
                   building, floor, room, first_half_semester, second_half_semester, biweekly, inherited_from)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            slot_rows,
        )
        dst.execute(
            """UPDATE vvz_units SET weekly_hours = (
                   SELECT COALESCE(SUM(hours), 0) FROM vvz_courses c
                   WHERE c.unit_id = vvz_units.id AND c.hour_type = 'WEEKLY_HOURS')"""
        )

        # Lecturers: only the ones linked to a selected unit.
        dst.execute("CREATE TEMP TABLE sel (id INTEGER PRIMARY KEY)")
        dst.executemany("INSERT INTO sel VALUES (?)", [(i,) for i in unit_ids])
        link_rows = []
        for table, role in (("unitlecturerlink", "lecturer"), ("unitexaminerlink", "examiner")):
            for r in src.execute(f"SELECT unit_id, lecturer_id FROM {table}"):
                if r["unit_id"] in known:
                    link_rows.append((r["unit_id"], r["lecturer_id"], role))
        lecturer_ids = {lid for _, lid, _ in link_rows}
        dst.executemany(
            "INSERT OR IGNORE INTO vvz_lecturers (id, title, name, surname, department) VALUES (?,?,?,?,?)",
            [
                (r["id"], r["title"], r["name"], r["surname"], r["department"])
                for r in src.execute("SELECT * FROM lecturer") if r["id"] in lecturer_ids
            ],
        )
        dst.executemany("INSERT OR IGNORE INTO vvz_unit_lecturers (unit_id, lecturer_id, role) VALUES (?,?,?)", link_rows)
        counts["lecturers"] = len(lecturer_ids)

        paths = {r["id"]: (r["path_en"], r["path_de"]) for r in src.execute("SELECT id, path_en, path_de FROM sectionpathview")}
        section_rows = [
            (r["unit_id"], r["section_id"], r["type"], *paths.get(r["section_id"], (None, None)))
            for r in src.execute("SELECT unit_id, section_id, type FROM unitsectionlink") if r["unit_id"] in known
        ]
        dst.executemany("INSERT OR IGNORE INTO vvz_unit_sections (unit_id, section_id, type, path_en, path_de) VALUES (?,?,?,?,?)", section_rows)
        counts["sections"] = len(section_rows)

        numbers = {u["number"] for u in units}
        dst.executemany(
            "INSERT OR IGNORE INTO vvz_ratings (number, recommended, engaging, difficulty, effort, resources) VALUES (?,?,?,?,?,?)",
            [
                (r["course_number"], r["recommended"], r["engaging"], r["difficulty"], r["effort"], r["resources"])
                for r in src.execute("SELECT * FROM rating") if r["course_number"] in numbers
            ],
        )

        meta = dict(meta or {})
        meta.update(semesters=",".join(semesters), built_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **{f"count_{k}": v for k, v in counts.items()})
        dst.executemany("INSERT OR REPLACE INTO vvz_meta (key, value) VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
        dst.commit()
    finally:
        src.close()
        dst.close()

    os.replace(tmp_path, dest_path)
    return counts


# ---------------------------------------------------------------- sync


def current_meta(db_path: str) -> dict:
    if not os.path.exists(db_path):
        return {}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            return dict(db.execute("SELECT key, value FROM vvz_meta").fetchall())
    except sqlite3.Error:
        return {}


def sync(force: bool = False, semesters: list[str] | None = None, dump_path: str | None = None, db_path: str = DB_PATH) -> bool:
    """Refresh db_path from the latest dump. Returns True if a new database was built."""
    semesters = semesters or configured_semesters()
    have = current_meta(db_path)

    if dump_path:
        remote = {"source": dump_path}
    else:
        metadata = fetch_metadata()
        remote = {"source": f"{API_BASE}/api/v2/dump", "dump_last_modified_ms": str(metadata.get("last_modified_ms", "")), "dump_size_in_bytes": str(metadata.get("size_in_bytes", ""))}
        unchanged = have.get("dump_last_modified_ms") == remote["dump_last_modified_ms"] and have.get("semesters") == ",".join(semesters)
        if unchanged and not force:
            log.info("VVZ data is up to date (dump from %s, semesters %s)", have.get("dump_last_modified_ms"), have.get("semesters"))
            return False

    with tempfile.TemporaryDirectory(prefix="vvz-dump-") as tmp:
        source = dump_path or download_dump(tmp)
        log.info("Building %s for semesters %s", db_path, ", ".join(semesters))
        counts = build_db(source, db_path, semesters, meta=remote)
    log.info("Built %s: %s", db_path, ", ".join(f"{v} {k}" for k, v in counts.items()))
    return True


def run_loop(interval: int = REFRESH_SECONDS, **kwargs) -> None:
    """Sync now and then once per interval; on failure retry sooner. Runs forever."""
    while True:
        try:
            sync(**kwargs)
            wait = interval
        except Exception:  # noqa: BLE001 - keep the loop alive whatever happens
            log.exception("VVZ sync failed, retrying in %s s", RETRY_SECONDS)
            wait = min(RETRY_SECONDS, interval)
        time.sleep(wait)


def start_background(db_path: str = DB_PATH, interval: int = REFRESH_SECONDS) -> threading.Thread:
    """Run run_loop in a daemon thread. The app does this at start; one gunicorn worker, so no races."""
    if not logging.getLogger().handlers:
        # Under gunicorn nothing has configured logging yet; make the sync visible in `docker compose logs`.
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    thread = threading.Thread(target=run_loop, kwargs={"interval": interval, "db_path": db_path}, name="vvz-sync", daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="rebuild even if the dump has not changed")
    parser.add_argument("--loop", action="store_true", help="keep running and refresh every VVZ_REFRESH_SECONDS")
    parser.add_argument("--dump", metavar="PATH", help="build from a local dump (SQLite file) instead of downloading")
    parser.add_argument("--semesters", metavar="LIST", help="comma-separated, e.g. 2025W,2026S (default: env VVZ_SEMESTERS or auto)")
    parser.add_argument("--db", metavar="PATH", default=DB_PATH, help=f"output database (default: {DB_PATH})")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    semesters = configured_semesters(args.semesters)
    if args.loop:
        run_loop(force=args.force, semesters=semesters, dump_path=args.dump, db_path=args.db)
    sync(force=args.force, semesters=semesters, dump_path=args.dump, db_path=args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
