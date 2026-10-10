-- Every table the app uses. Add new tables here; their starting data goes in backend/seed/.

-- Identity comes from the reverse proxy, which authenticates every request and sends
-- X-User-Id (the email) and X-User-Name. A row is created the first time we see an email;
-- there are no passwords in this app.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    birth_date TEXT,                  -- 'YYYY-MM-DD'; age is computed from it
    study_start TEXT,                 -- 'YYYY-MM-DD'
    selected_semkez TEXT              -- the semester the app shows, e.g. '2026W'; NULL = the current one
);

-- Course catalog, shared by all users. One row per ETH unit number (code), across semesters.
-- Rows come from the seed and from the VVZ sync (backend/vvz/), which upserts by code and
-- fills the columns below from the catalogue; semester-specific detail is in course_offerings.
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,        -- e.g. '252-0027-00L'
    title TEXT NOT NULL,
    term TEXT CHECK (term IN ('HS', 'FS')),   -- of the latest offering
    ects INTEGER NOT NULL,
    professor TEXT,                   -- lecturers of the latest offering, comma-separated
    -- Filled by the VVZ sync; NULL for courses only the seed knows.
    title_english TEXT,
    language TEXT,
    exam_mode TEXT,                   -- 'written 180 minutes'
    exam_type TEXT,                   -- 'session examination', 'end-of-semester examination', ...
    exam_block TEXT,                  -- JSON list; first-year courses name their Basisprüfung block
    course_frequency TEXT,            -- ANNUAL, SEMESTER, BIENNIAL, ONETIME
    weekly_hours REAL,                -- lecture + exercise hours per week of the latest offering
    levels TEXT,                      -- JSON list, e.g. ["BSC"]
    departments TEXT,                 -- JSON list of VVZ department ids
    abstract TEXT,
    objective TEXT,
    content TEXT,
    lecture_notes TEXT,
    literature TEXT,
    written_aids TEXT,
    latest_semkez TEXT,               -- '2026W' = autumn 2026, '2027S' = spring 2027
    vvz_updated_at TEXT               -- when the sync last wrote this row
);

-- One course as offered in one semester, from VVZ. id is the VVZ lerneinheitId.
CREATE TABLE IF NOT EXISTS course_offerings (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    semkez TEXT NOT NULL,
    title TEXT,
    ects REAL,
    max_places INTEGER,
    weekly_hours REAL,                -- sum over course_lectures with WEEKLY_HOURS
    UNIQUE (course_id, semkez)
);
CREATE INDEX IF NOT EXISTS course_offerings_semkez ON course_offerings (semkez);

-- The parts of an offering with their own hours and rooms: the lecture (V), the exercise (U), ...
CREATE TABLE IF NOT EXISTS course_lectures (
    offering_id INTEGER NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    number TEXT NOT NULL,             -- '401-0212-16 V'
    title TEXT,
    type TEXT,                        -- V, U, G, P, S, K, A, D, R
    type_name TEXT,                   -- 'lecture', 'exercise', ...
    hours REAL,
    hour_type TEXT,                   -- WEEKLY_HOURS or SEMESTER_HOURS
    comment TEXT,
    PRIMARY KEY (offering_id, number)
);

CREATE TABLE IF NOT EXISTS course_timeslots (
    id INTEGER PRIMARY KEY,
    offering_id INTEGER NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    lecture_number TEXT NOT NULL,     -- course_lectures.number
    weekday INTEGER,                  -- 0 = Monday ... 6 = Sunday
    date TEXT,                        -- '31.12' for one-off slots, else NULL
    start_time TEXT,                  -- '14:15'
    end_time TEXT,                    -- '16:00'
    building TEXT,                    -- 'HG'
    floor TEXT,                       -- 'F'
    room TEXT,                        -- '1'
    first_half_semester INTEGER NOT NULL DEFAULT 0,
    second_half_semester INTEGER NOT NULL DEFAULT 0,
    biweekly INTEGER NOT NULL DEFAULT 0,
    inherited_from TEXT               -- NULL = real slot; else the semkez it was copied from (see vvz/sync.py)
);
CREATE INDEX IF NOT EXISTS course_timeslots_offering ON course_timeslots (offering_id);

CREATE TABLE IF NOT EXISTS lecturers (
    id INTEGER PRIMARY KEY,           -- VVZ id
    title TEXT,                       -- 'Prof. Dr.'
    name TEXT,
    surname TEXT,
    department TEXT
);

CREATE TABLE IF NOT EXISTS course_lecturers (
    offering_id INTEGER NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    lecturer_id INTEGER NOT NULL REFERENCES lecturers(id),
    role TEXT NOT NULL,               -- 'lecturer' or 'examiner'
    PRIMARY KEY (offering_id, lecturer_id, role)
);

-- Where an offering sits in a programme, e.g.
-- 'Computer Science Bachelor > First Year Examinations > First Year Examination Block 1'
CREATE TABLE IF NOT EXISTS course_sections (
    offering_id INTEGER NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL,
    type TEXT,                        -- O (compulsory), W (elective), W+, E-, Z, Dr
    path_en TEXT,
    path_de TEXT,
    PRIMARY KEY (offering_id, section_id)
);
CREATE INDEX IF NOT EXISTS course_sections_path ON course_sections (path_en);

-- Student ratings scraped from course reviews, by course code.
CREATE TABLE IF NOT EXISTS course_ratings (
    code TEXT PRIMARY KEY,
    recommended REAL,
    engaging REAL,
    difficulty REAL,
    effort REAL,
    resources REAL
);

-- What the VVZ sync last imported (dump timestamp, semesters, counts).
CREATE TABLE IF NOT EXISTS vvz_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Resources and docs of a course (a list per course)
CREATE TABLE IF NOT EXISTS course_resources (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('resource', 'doc')),
    title TEXT NOT NULL,
    url TEXT
);

-- A user's semesters
CREATE TABLE IF NOT EXISTS semesters (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label TEXT NOT NULL,              -- e.g. 'HS26'
    study_hours_per_week INTEGER,     -- the week's study budget; NULL = planner.DEFAULT_HOURS_PER_WEEK
    -- How the scheduler lays a day out (backend/schedule_planner/). Defaults make a new
    -- semester plannable before the user has said anything about their habits.
    day_start TEXT NOT NULL DEFAULT '08:00',
    day_end TEXT NOT NULL DEFAULT '20:00',
    lunch_start TEXT NOT NULL DEFAULT '12:00',
    lunch_end TEXT NOT NULL DEFAULT '13:00',
    dinner_start TEXT NOT NULL DEFAULT '18:00',
    dinner_end TEXT NOT NULL DEFAULT '19:00',
    study_block_size INTEGER NOT NULL DEFAULT 90,   -- minutes
    alpha REAL NOT NULL DEFAULT 0.3,  -- weight of difficulty against priority
    beta REAL NOT NULL DEFAULT 5,     -- how hard a near exam pulls hours forward
    UNIQUE (user_id, label),
    UNIQUE (id, user_id)              -- target for the statistics foreign key
);

-- Days the user does not study, as ranges: one row per holiday or break.
CREATE TABLE IF NOT EXISTS semester_days_off (
    semester_id INTEGER NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,         -- 'YYYY-MM-DD'
    range_length INTEGER NOT NULL DEFAULT 1 CHECK (range_length >= 1),
    PRIMARY KEY (semester_id, start_date)
);

-- Courses a user takes in a semester, plus their plan for it. In the app each one is a
-- subject with id 'course-<course_id>'. Columns added later are also listed in
-- db.ADDED_COLUMNS, so an older database gets them too.
CREATE TABLE IF NOT EXISTS semester_courses (
    semester_id INTEGER NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    desired_grade REAL CHECK (desired_grade BETWEEN 1 AND 6),
    target_hours REAL NOT NULL DEFAULT 0,
    exam_date TEXT,                   -- 'YYYY-MM-DD'
    completed INTEGER NOT NULL DEFAULT 0,
    next_action TEXT NOT NULL DEFAULT '',
    color TEXT,                       -- '#2598A2'
    -- What the scheduler needs beyond the catalogue. NULL falls back to the VVZ value, or
    -- to course_ratings.difficulty, or to the middle of the scale; see planner.py.
    priority INTEGER NOT NULL DEFAULT 3,   -- 1 (most important) to 5
    difficulty INTEGER,                    -- 1 (easy) to 5
    max_study_hours REAL,                  -- cap on active learning; recall is exempt
    lecture_per_week REAL,                 -- contact hours a week, else the offering's
    PRIMARY KEY (semester_id, course_id)
);

-- Hours the user recorded for a course on a day. No row = nothing recorded (not 0).
CREATE TABLE IF NOT EXISTS study_hours (
    semester_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    date TEXT NOT NULL,               -- 'YYYY-MM-DD'
    hours REAL NOT NULL CHECK (hours BETWEEN 0 AND 24),
    PRIMARY KEY (semester_id, course_id, date),
    FOREIGN KEY (semester_id, course_id) REFERENCES semester_courses(semester_id, course_id) ON DELETE CASCADE
);

-- Study sessions the user planned in the calendar. id is the uuid the browser generates.
CREATE TABLE IF NOT EXISTS study_sessions (
    semester_id INTEGER NOT NULL,
    id TEXT NOT NULL,
    course_id INTEGER NOT NULL,
    date TEXT NOT NULL,               -- 'YYYY-MM-DD'
    start TEXT NOT NULL,              -- 'HH:MM'
    hours REAL NOT NULL CHECK (hours > 0 AND hours <= 24),
    PRIMARY KEY (semester_id, id),
    FOREIGN KEY (semester_id, course_id) REFERENCES semester_courses(semester_id, course_id) ON DELETE CASCADE
);

-- The generated study plan of a semester, one row: regenerating replaces it.
CREATE TABLE IF NOT EXISTS study_plans (
    semester_id INTEGER PRIMARY KEY REFERENCES semesters(id) ON DELETE CASCADE,
    generated_at TEXT NOT NULL,       -- ISO timestamp of the run
    from_date TEXT NOT NULL,          -- first day this run planned; earlier blocks are history
    input_json TEXT NOT NULL,         -- what went into generate_schedule(), so a run is reproducible
    summary_json TEXT NOT NULL        -- the scheduler's summary block
);

-- The blocks of that plan. A meal block has no course. Dropping a course drops its blocks:
-- SQLite does not enforce a composite foreign key when a column of it is NULL, so meals pass.
CREATE TABLE IF NOT EXISTS plan_blocks (
    id INTEGER PRIMARY KEY,
    semester_id INTEGER NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    course_id INTEGER,
    date TEXT NOT NULL,               -- 'YYYY-MM-DD'
    start_time TEXT NOT NULL,         -- 'HH:MM'
    end_time TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('active_learning', 'recall', 'meal')),
    label TEXT,                       -- 'Lunch' for a meal block
    FOREIGN KEY (semester_id, course_id) REFERENCES semester_courses(semester_id, course_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS plan_blocks_semester_date ON plan_blocks (semester_id, date);

-- Statistics per user and semester
CREATE TABLE IF NOT EXISTS statistics (
    user_id INTEGER NOT NULL,
    semester_id INTEGER NOT NULL,
    -- statistic columns go here
    PRIMARY KEY (user_id, semester_id),
    -- the semester must belong to the same user
    FOREIGN KEY (semester_id, user_id) REFERENCES semesters(id, user_id) ON DELETE CASCADE
);

-- A user's file library per subject: folders, lecture PDFs and small text notes.
-- The PDF bytes are not in here; they live in the pipeline's folder for the same id
-- (DATA_DIR/learning/<id>/source.pdf), so an upload is stored exactly once.
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,              -- the uuid the browser generates
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL,         -- the subject's id in the frontend's study data
    parent_id TEXT REFERENCES materials(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('folder', 'pdf', 'md', 'txt')),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    -- Document purpose; kind remains the storage format. NULL for folders and
    -- unclassified legacy notes/books/transcripts. Generated types are reserved.
    type TEXT CHECK (type IS NULL OR (type IN ('slides', 'mock_exam', 'exercise', 'exercise_solution',
                              'script', 'summary', 'cards', 'mcq') AND kind <> 'folder')),
    marker TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    content TEXT,                     -- md and txt only; PDFs keep their bytes on disk
    sha256 TEXT,                      -- of the stored PDF
    added_at INTEGER NOT NULL,        -- milliseconds since the epoch
    -- Summaries, flashcards and the state of the last pipeline run, as the JSON the
    -- frontend sends. The server stores them whole and never reads inside them.
    outputs TEXT,
    processing TEXT
);

-- One name per folder, per subject, per user, ignoring case. ifnull() covers the root,
-- where parent_id is NULL and NULLs would otherwise all count as different.
CREATE UNIQUE INDEX IF NOT EXISTS materials_unique_name
    ON materials (user_id, subject_id, ifnull(parent_id, ''), lower(name));

-- A user's to-do list per subject, like Google Tasks: add, tick off, edit, reorder, delete.
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,              -- the uuid the browser generates
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL,         -- the subject's id in the frontend's study data
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    due TEXT,                         -- 'YYYY-MM-DD' or NULL
    done INTEGER NOT NULL DEFAULT 0,
    completed_at INTEGER,             -- milliseconds since the epoch, NULL while open
    position REAL NOT NULL,           -- manual order among open tasks, ascending
    created_at INTEGER NOT NULL       -- milliseconds since the epoch
);
CREATE INDEX IF NOT EXISTS tasks_by_subject ON tasks (user_id, subject_id);
