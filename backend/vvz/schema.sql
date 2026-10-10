-- Local copy of the ETH course catalogue (VVZ), built by `python -m vvz.sync`
-- from the vvzapi.ch database dump. This file lives next to app.db but is NOT
-- part of reset-db: it is rebuilt by the sync, not from seed files.
--
-- Vocabulary (same as VVZ): a "unit" (Lerneinheit) is what students call a
-- course, e.g. "Analysis I" with 7 ECTS. A "course" (Lehrveranstaltung) is one
-- part of it with its own hours and timeslots: the lecture (V), the exercise
-- (U), a lab (P), ...

CREATE TABLE IF NOT EXISTS vvz_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS vvz_units (
    id               INTEGER PRIMARY KEY,   -- VVZ lerneinheitId, unique per semester
    semkez           TEXT NOT NULL,         -- "2025W" = autumn 2025, "2026S" = spring 2026
    number           TEXT,                  -- "401-0212-16L", stable across semesters
    title            TEXT,
    title_english    TEXT,
    credits          REAL,                  -- ECTS
    levels           TEXT,                  -- JSON list, e.g. ["BSC"]
    departments      TEXT,                  -- JSON list of department ids
    language         TEXT,
    exam_mode        TEXT,                  -- "written 180 minutes"
    exam_type        TEXT,                  -- "session examination", "end-of-semester examination", ...
    exam_block       TEXT,                  -- JSON list; first-year courses name their Basisprüfung block here
    course_frequency TEXT,                  -- ANNUAL, SEMESTER, BIENNIAL, ONETIME
    max_places       INTEGER,
    abstract         TEXT,
    objective        TEXT,
    content          TEXT,
    lecture_notes    TEXT,
    literature       TEXT,
    written_aids     TEXT,
    weekly_hours     REAL                   -- sum of WEEKLY_HOURS over the unit's courses, for planning
);
CREATE INDEX IF NOT EXISTS ix_vvz_units_semkez ON vvz_units (semkez);
CREATE INDEX IF NOT EXISTS ix_vvz_units_number ON vvz_units (number);
CREATE INDEX IF NOT EXISTS ix_vvz_units_title  ON vvz_units (title);

CREATE TABLE IF NOT EXISTS vvz_courses (
    number    TEXT NOT NULL,                -- "401-0212-16 V"
    semkez    TEXT NOT NULL,
    unit_id   INTEGER NOT NULL REFERENCES vvz_units (id) ON DELETE CASCADE,
    title     TEXT,
    type      TEXT,                         -- V, U, G, P, S, K, A, D, R
    type_name TEXT,                         -- "lecture", "exercise", ...
    hours     REAL,
    hour_type TEXT,                         -- WEEKLY_HOURS or SEMESTER_HOURS
    comment   TEXT,
    PRIMARY KEY (number, semkez, unit_id)
);
CREATE INDEX IF NOT EXISTS ix_vvz_courses_unit ON vvz_courses (unit_id);

CREATE TABLE IF NOT EXISTS vvz_timeslots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id              INTEGER NOT NULL REFERENCES vvz_units (id) ON DELETE CASCADE,
    course_number        TEXT NOT NULL,
    semkez               TEXT NOT NULL,
    weekday              INTEGER,           -- 0 = Monday ... 6 = Sunday
    date                 TEXT,              -- "31.12" for one-off slots, else NULL
    start_time           TEXT,              -- "14:15"
    end_time             TEXT,              -- "16:00"
    building             TEXT,              -- "HG"
    floor                TEXT,              -- "F"
    room                 TEXT,              -- "1"
    first_half_semester  INTEGER NOT NULL DEFAULT 0,
    second_half_semester INTEGER NOT NULL DEFAULT 0,
    biweekly             INTEGER NOT NULL DEFAULT 0,
    inherited_from       TEXT               -- NULL = real slot; else the semkez the slot was copied from (see sync.py)
);
CREATE INDEX IF NOT EXISTS ix_vvz_timeslots_unit ON vvz_timeslots (unit_id);

CREATE TABLE IF NOT EXISTS vvz_lecturers (
    id         INTEGER PRIMARY KEY,
    title      TEXT,                        -- "Prof. Dr."
    name       TEXT,
    surname    TEXT,
    department TEXT
);

CREATE TABLE IF NOT EXISTS vvz_unit_lecturers (
    unit_id     INTEGER NOT NULL REFERENCES vvz_units (id) ON DELETE CASCADE,
    lecturer_id INTEGER NOT NULL REFERENCES vvz_lecturers (id),
    role        TEXT NOT NULL,              -- "lecturer" or "examiner"
    PRIMARY KEY (unit_id, lecturer_id, role)
);

-- Where a unit sits in a programme, e.g.
-- "Computer Science Bachelor > 1. Semester Bachelor Programme > First Year Examinations (1. Sem.)"
CREATE TABLE IF NOT EXISTS vvz_unit_sections (
    unit_id    INTEGER NOT NULL REFERENCES vvz_units (id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL,
    type       TEXT,                        -- O (compulsory), W (elective), W+, E-, Z, Dr
    path_en    TEXT,
    path_de    TEXT,
    PRIMARY KEY (unit_id, section_id)
);
CREATE INDEX IF NOT EXISTS ix_vvz_unit_sections_path ON vvz_unit_sections (path_en);

-- Student ratings scraped from course reviews, keyed by unit number (not semester).
CREATE TABLE IF NOT EXISTS vvz_ratings (
    number      TEXT PRIMARY KEY,
    recommended REAL,
    engaging    REAL,
    difficulty  REAL,
    effort      REAL,
    resources   REAL
);
