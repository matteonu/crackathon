"""Fill the course catalogue in the app database from the ETH VVZ.

The data comes from the community project vvzapi.ch (https://github.com/markbeep/vvzapi),
which scrapes vvz.ethz.ch and publishes a full database dump. We download that dump, keep
the semesters we care about, and import them into our own tables (see schema.sql): `courses`
is upserted by code, so rows the seed created and rows users reference keep their ids;
`course_offerings` and its children are replaced per semester.

The downloaded dump is cached in DATA_DIR (vvz-dump.zip), so a reset-db can refill the
catalogue in a second without the network.

Usage (from backend/):
    python -m vvz.sync                 # download if the dump changed, then import
    python -m vvz.sync --force         # import even if nothing changed
    python -m vvz.sync --offline       # import from the cached dump only, no network
    python -m vvz.sync --loop          # keep running and refresh every VVZ_REFRESH_SECONDS
    python -m vvz.sync --dump path.db  # import from a dump file you already have
    python -m vvz.sync --semesters 2025W,2026S

Environment:
    DATABASE_PATH        the app database (default: $DATA_DIR/app.db)
    DATA_DIR             where the dump cache lives (default: backend/data)
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
SCHEMA_PATH = os.path.join(BACKEND_DIR, "schema.sql")
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(BACKEND_DIR, "data")
DATABASE_PATH = os.environ.get("DATABASE_PATH") or os.path.join(DATA_DIR, "app.db")
API_BASE = os.environ.get("VVZ_API_BASE", "https://vvzapi.ch").rstrip("/")
REFRESH_SECONDS = int(os.environ.get("VVZ_REFRESH_SECONDS", "86400"))
RETRY_SECONDS = 1800
CACHE_NAME = "vvz-dump.zip"
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


def term_of(semkez: str) -> str:
    """The app's term label: W (Wintersemester) is HS, S is FS."""
    return "HS" if semkez.endswith("W") else "FS"


def default_semesters(today: dt.date | None = None, before: int = 1, after: int = 2) -> list[str]:
    current = semester_of(today or dt.date.today())
    return [shift_semester(current, i) for i in range(-before, after + 1)]


def configured_semesters(arg: str | None = None) -> list[str]:
    raw = arg or os.environ.get("VVZ_SEMESTERS", "")
    if raw.strip():
        return [s.strip().upper() for s in raw.split(",") if s.strip()]
    return default_semesters()


# ---------------------------------------------------------------- download and cache


def fetch_metadata() -> dict:
    req = urllib.request.Request(f"{API_BASE}/api/v2/dump/metadata", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def cache_paths(data_dir: str) -> tuple[str, str]:
    return os.path.join(data_dir, CACHE_NAME), os.path.join(data_dir, CACHE_NAME + ".json")


def cached_dump_info(data_dir: str) -> dict:
    zip_path, info_path = cache_paths(data_dir)
    if not (os.path.exists(zip_path) and os.path.exists(info_path)):
        return {}
    try:
        with open(info_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def download_dump(data_dir: str, metadata: dict) -> str:
    """Download the dump zip into the cache (atomically) and remember which version it is."""
    os.makedirs(data_dir, exist_ok=True)
    zip_path, info_path = cache_paths(data_dir)
    req = urllib.request.Request(f"{API_BASE}/api/v2/dump", headers={"User-Agent": USER_AGENT})
    log.info("Downloading %s/api/v2/dump", API_BASE)
    with urllib.request.urlopen(req, timeout=600) as resp, open(zip_path + ".part", "wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)
    os.replace(zip_path + ".part", zip_path)
    with open(info_path, "w") as f:
        json.dump({"dump_last_modified_ms": str(metadata.get("last_modified_ms", "")),
                   "dump_size_in_bytes": str(metadata.get("size_in_bytes", "")),
                   "downloaded_at": _now()}, f)
    return zip_path


def extract_dump(zip_path: str, dest_dir: str) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        if not members:
            raise RuntimeError("The dump zip is empty")
        zf.extract(members[0], dest_dir)
        return os.path.join(dest_dir, members[0])


# ---------------------------------------------------------------- import


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


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


def _slot_rows(offering_id: int, lecture_number: str, timeslots_json, inherited_from: str | None = None) -> list[tuple]:
    rows = []
    for s in json.loads(_json_list(timeslots_json)):
        if not isinstance(s, dict):
            continue
        rows.append((
            offering_id, lecture_number, s.get("weekday"), s.get("date"),
            s.get("start_time"), s.get("end_time"), s.get("building"), s.get("floor"), s.get("room"),
            int(bool(s.get("first_half_semester"))), int(bool(s.get("second_half_semester"))),
            int(bool(s.get("biweekly"))), inherited_from,
        ))
    return rows


def _prefer_english(row, column: str):
    return row[f"{column}_english"] or row[column]


def _lecturer_names(lecturers: list[sqlite3.Row]) -> str | None:
    names = [" ".join(p for p in (r["title"], r["name"], r["surname"]) if p) for r in lecturers]
    return ", ".join(names) or None


def import_dump(source_path: str, db_path: str, semesters: list[str], meta: dict | None = None) -> dict:
    """Import the given semesters from a vvzapi dump into the app database. Returns row counts.

    Everything happens in one transaction, so a reader sees either the old or the new
    catalogue. Courses are upserted by code (ids survive); offerings of the selected
    semesters are deleted and re-inserted, which cascades to their lectures, timeslots,
    lecturer links and sections.
    """
    if not semesters:
        raise ValueError("No semesters selected")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    src = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    dst.row_factory = sqlite3.Row
    try:
        with open(SCHEMA_PATH) as f:
            dst.executescript(f.read())  # idempotent; lets the CLI run before the app ever did
        dst.execute("PRAGMA foreign_keys = ON")
        dst.execute("BEGIN")
        marks = ",".join("?" for _ in semesters)
        counts = {"courses": 0, "offerings": 0, "lectures": 0, "timeslots": 0, "inherited_timeslots": 0, "lecturers": 0, "sections": 0}
        now = _now()

        # The dump occasionally lists the same unit twice in one semester under two ids (a
        # handful per semester, identical content); the newest id wins so an offering is unique
        # per course and semester.
        by_key = {}
        for u in src.execute(
            f"SELECT * FROM learningunit WHERE semkez IN ({marks}) AND number IS NOT NULL ORDER BY semkez, number, id",
            semesters,
        ):
            by_key[(u["number"], u["semkez"])] = u
        units = list(by_key.values())
        unit_ids = {u["id"] for u in units}

        # Lecturers of the selected units, used both for the offerings and for courses.professor.
        links = {}  # unit_id -> [(lecturer_id, role)]
        for table, role in (("unitlecturerlink", "lecturer"), ("unitexaminerlink", "examiner")):
            for r in src.execute(f"SELECT unit_id, lecturer_id FROM {table}"):
                if r["unit_id"] in unit_ids:
                    links.setdefault(r["unit_id"], []).append((r["lecturer_id"], role))
        lecturer_ids = {lid for pairs in links.values() for lid, _ in pairs}
        lecturers = {r["id"]: r for r in src.execute("SELECT * FROM lecturer") if r["id"] in lecturer_ids}
        dst.executemany(
            """INSERT INTO lecturers (id, title, name, surname, department) VALUES (?,?,?,?,?)
               ON CONFLICT (id) DO UPDATE SET title = excluded.title, name = excluded.name,
                   surname = excluded.surname, department = excluded.department""",
            [(r["id"], r["title"], r["name"], r["surname"], r["department"]) for r in lecturers.values()],
        )
        counts["lecturers"] = len(lecturers)

        # Courses: one row per code, filled from the latest selected offering of that code.
        dst.execute(f"DELETE FROM course_offerings WHERE semkez IN ({marks})", semesters)
        latest = {}
        for u in units:
            if u["number"] not in latest or u["semkez"] > latest[u["number"]]["semkez"]:
                latest[u["number"]] = u
        for u in latest.values():
            teachers = [lecturers[lid] for lid, role in links.get(u["id"], []) if role == "lecturer" and lid in lecturers]
            dst.execute(
                """INSERT INTO courses (code, title, term, ects, professor, title_english, language, exam_mode,
                       exam_type, exam_block, course_frequency, levels, departments, abstract, objective,
                       content, lecture_notes, literature, written_aids, latest_semkez, vvz_updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT (code) DO UPDATE SET
                       title = excluded.title, term = excluded.term, ects = excluded.ects,
                       professor = COALESCE(excluded.professor, courses.professor),
                       title_english = excluded.title_english, language = excluded.language,
                       exam_mode = excluded.exam_mode, exam_type = excluded.exam_type,
                       exam_block = excluded.exam_block, course_frequency = excluded.course_frequency,
                       levels = excluded.levels, departments = excluded.departments,
                       abstract = excluded.abstract, objective = excluded.objective, content = excluded.content,
                       lecture_notes = excluded.lecture_notes, literature = excluded.literature,
                       written_aids = excluded.written_aids, latest_semkez = excluded.latest_semkez,
                       vvz_updated_at = excluded.vvz_updated_at
                   WHERE courses.latest_semkez IS NULL OR excluded.latest_semkez >= courses.latest_semkez""",
                (
                    u["number"], u["title_english"] or u["title"], term_of(u["semkez"]), u["credits"] or 0,
                    _lecturer_names(teachers), u["title_english"], u["language"], u["exam_mode"], u["exam_type"],
                    _json_list(u["exam_block"]), u["course_frequency"], _json_list(u["levels"]),
                    _json_list(u["departments"]), _prefer_english(u, "abstract"), _prefer_english(u, "objective"),
                    _prefer_english(u, "content"), _prefer_english(u, "lecture_notes"),
                    _prefer_english(u, "literature"), u["written_aids"], u["semkez"], now,
                ),
            )
        counts["courses"] = len(latest)
        course_ids = {r["code"]: r["id"] for r in dst.execute("SELECT id, code FROM courses")}

        # Offerings, lectures, timeslots, lecturer links, sections.
        paths = {r["id"]: (r["path_en"], r["path_de"]) for r in src.execute("SELECT id, path_en, path_de FROM sectionpathview")}
        sections = {}
        for r in src.execute("SELECT unit_id, section_id, type FROM unitsectionlink"):
            if r["unit_id"] in unit_ids:
                sections.setdefault(r["unit_id"], []).append((r["section_id"], r["type"], *paths.get(r["section_id"], (None, None))))
        courses_by_unit = {}
        for c in src.execute(f"SELECT * FROM course WHERE semkez IN ({marks})", semesters):
            courses_by_unit.setdefault(c["unit_id"], []).append(c)

        for u in units:
            dst.execute(
                "INSERT INTO course_offerings (id, course_id, semkez, title, ects, max_places) VALUES (?,?,?,?,?,?)",
                (u["id"], course_ids[u["number"]], u["semkez"], u["title_english"] or u["title"], u["credits"], u["max_places"]),
            )
            counts["offerings"] += 1
            slot_rows = []
            for c in courses_by_unit.get(u["id"], []):
                dst.execute(
                    "INSERT OR IGNORE INTO course_lectures (offering_id, number, title, type, type_name, hours, hour_type, comment) VALUES (?,?,?,?,?,?,?,?)",
                    (u["id"], c["number"], c["title"], c["type"], COURSE_TYPE_NAMES.get(c["type"] or "", c["type"]), c["hours"], c["hour_type"], c["comment"]),
                )
                counts["lectures"] += 1
                slot_rows += _slot_rows(u["id"], c["number"], c["timeslots"])
            counts["timeslots"] += len(slot_rows)
            if not slot_rows:
                # vvzapi sometimes has no timeslots yet for a semester (all of 2026W at the time of
                # writing). ETH timetables are stable year to year, so copy the slots of the same
                # unit one year earlier and mark them as inherited.
                previous = shift_semester(u["semkez"], -2)
                for c in src.execute(
                    "SELECT c.* FROM course c JOIN learningunit l ON l.id = c.unit_id WHERE l.number = ? AND c.semkez = ?",
                    (u["number"], previous),
                ):
                    parts = c["number"].rsplit(" ", 1)
                    number = c["number"] if len(parts) < 2 else f"{u['number'][:-1]} {parts[1]}"
                    rows = _slot_rows(u["id"], number, c["timeslots"], inherited_from=previous)
                    slot_rows += rows
                    counts["inherited_timeslots"] += len(rows)
            dst.executemany(
                """INSERT INTO course_timeslots (offering_id, lecture_number, weekday, date, start_time, end_time,
                       building, floor, room, first_half_semester, second_half_semester, biweekly, inherited_from)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                slot_rows,
            )
            dst.executemany(
                "INSERT OR IGNORE INTO course_lecturers (offering_id, lecturer_id, role) VALUES (?,?,?)",
                [(u["id"], lid, role) for lid, role in links.get(u["id"], []) if lid in lecturers],
            )
            dst.executemany(
                "INSERT OR IGNORE INTO course_sections (offering_id, section_id, type, path_en, path_de) VALUES (?,?,?,?,?)",
                [(u["id"], *row) for row in sections.get(u["id"], [])],
            )
            counts["sections"] += len(sections.get(u["id"], []))

        dst.execute(
            f"""UPDATE course_offerings SET weekly_hours = (
                    SELECT COALESCE(SUM(hours), 0) FROM course_lectures l
                    WHERE l.offering_id = course_offerings.id AND l.hour_type = 'WEEKLY_HOURS')
                WHERE semkez IN ({marks})""", semesters,
        )
        dst.execute(
            """UPDATE courses SET weekly_hours = (
                   SELECT o.weekly_hours FROM course_offerings o
                   WHERE o.course_id = courses.id AND o.semkez = courses.latest_semkez)
               WHERE vvz_updated_at = ?""", (now,),
        )

        numbers = set(latest)
        dst.executemany(
            """INSERT INTO course_ratings (code, recommended, engaging, difficulty, effort, resources) VALUES (?,?,?,?,?,?)
               ON CONFLICT (code) DO UPDATE SET recommended = excluded.recommended, engaging = excluded.engaging,
                   difficulty = excluded.difficulty, effort = excluded.effort, resources = excluded.resources""",
            [
                (r["course_number"], r["recommended"], r["engaging"], r["difficulty"], r["effort"], r["resources"])
                for r in src.execute("SELECT * FROM rating") if r["course_number"] in numbers
            ],
        )

        meta = dict(meta or {})
        meta.update(semesters=",".join(semesters), built_at=now, **{f"count_{k}": v for k, v in counts.items()})
        dst.executemany("INSERT OR REPLACE INTO vvz_meta (key, value) VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
        dst.execute("COMMIT")
    except BaseException:
        if dst.in_transaction:
            dst.execute("ROLLBACK")
        raise
    finally:
        src.close()
        dst.close()
    return counts


# ---------------------------------------------------------------- sync


def current_meta(db_path: str) -> dict:
    if not os.path.exists(db_path):
        return {}
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return dict(db.execute("SELECT key, value FROM vvz_meta").fetchall())
        finally:
            db.close()
    except sqlite3.Error:
        return {}


def sync(force: bool = False, offline: bool = False, semesters: list[str] | None = None, dump_path: str | None = None,
         db_path: str = DATABASE_PATH, data_dir: str = DATA_DIR) -> bool:
    """Refresh the catalogue in db_path. Returns True if an import ran.

    Online: ask vvzapi.ch for the dump's timestamp, download it into the cache if it changed,
    and import unless the database already holds that version for these semesters.
    Offline: import from the cached dump (or dump_path) without touching the network;
    this is what reset-db uses, and it is a no-op when there is no cache yet.
    """
    semesters = semesters or configured_semesters()
    have = current_meta(db_path)
    zip_path, _ = cache_paths(data_dir)

    if dump_path:
        source_info = {"source": dump_path}
    elif offline:
        source_info = cached_dump_info(data_dir)
        if not source_info:
            log.info("No cached VVZ dump in %s; nothing to import offline", data_dir)
            return False
        source_info["source"] = zip_path
    else:
        metadata = fetch_metadata()
        wanted = str(metadata.get("last_modified_ms", ""))
        if cached_dump_info(data_dir).get("dump_last_modified_ms") != wanted:
            download_dump(data_dir, metadata)
        source_info = cached_dump_info(data_dir)
        source_info["source"] = f"{API_BASE}/api/v2/dump"

    unchanged = (
        have.get("dump_last_modified_ms") is not None
        and have.get("dump_last_modified_ms") == source_info.get("dump_last_modified_ms")
        and have.get("semesters") == ",".join(semesters)
    )
    if unchanged and not force:
        log.info("Catalogue is up to date (dump %s, semesters %s)", have.get("dump_last_modified_ms"), have.get("semesters"))
        return False

    with tempfile.TemporaryDirectory(prefix="vvz-dump-") as tmp:
        source = dump_path or extract_dump(zip_path, tmp)
        log.info("Importing semesters %s into %s", ", ".join(semesters), db_path)
        counts = import_dump(source, db_path, semesters, meta={k: v for k, v in source_info.items() if k != "downloaded_at"})
    log.info("Imported: %s", ", ".join(f"{v} {k}" for k, v in counts.items()))
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


def start_background(db_path: str = DATABASE_PATH, data_dir: str = DATA_DIR, interval: int = REFRESH_SECONDS) -> threading.Thread:
    """Run run_loop in a daemon thread. The app does this at start; one gunicorn worker, so no races."""
    if not logging.getLogger().handlers:
        # Under gunicorn nothing has configured logging yet; make the sync visible in `docker compose logs`.
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    thread = threading.Thread(target=run_loop, kwargs={"interval": interval, "db_path": db_path, "data_dir": data_dir}, name="vvz-sync", daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="import even if the dump has not changed")
    parser.add_argument("--offline", action="store_true", help="import from the cached dump, no network")
    parser.add_argument("--loop", action="store_true", help="keep running and refresh every VVZ_REFRESH_SECONDS")
    parser.add_argument("--dump", metavar="PATH", help="import from this dump (SQLite file) instead of the cache")
    parser.add_argument("--semesters", metavar="LIST", help="comma-separated, e.g. 2025W,2026S (default: env VVZ_SEMESTERS or auto)")
    parser.add_argument("--db", metavar="PATH", default=DATABASE_PATH, help=f"app database (default: {DATABASE_PATH})")
    parser.add_argument("--data-dir", metavar="PATH", default=DATA_DIR, help=f"dump cache directory (default: {DATA_DIR})")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    kwargs = dict(force=args.force, offline=args.offline, semesters=configured_semesters(args.semesters),
                  dump_path=args.dump, db_path=args.db, data_dir=args.data_dir)
    if args.loop:
        run_loop(**kwargs)
    sync(**kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
