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
    study_start TEXT                  -- 'YYYY-MM-DD'
);

-- Course catalog, shared by all users
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,        -- e.g. '252-0027-00L'
    title TEXT NOT NULL,
    term TEXT CHECK (term IN ('HS', 'FS')),
    ects INTEGER NOT NULL,
    professor TEXT
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
    study_hours_per_week INTEGER,
    UNIQUE (user_id, label),
    UNIQUE (id, user_id)              -- target for the statistics foreign key
);

-- Courses a user takes in a semester, plus values known during the semester
CREATE TABLE IF NOT EXISTS semester_courses (
    semester_id INTEGER NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    desired_grade REAL CHECK (desired_grade BETWEEN 1 AND 6),
    PRIMARY KEY (semester_id, course_id)
);

-- Statistics per user and semester
CREATE TABLE IF NOT EXISTS statistics (
    user_id INTEGER NOT NULL,
    semester_id INTEGER NOT NULL,
    -- statistic columns go here
    PRIMARY KEY (user_id, semester_id),
    -- the semester must belong to the same user
    FOREIGN KEY (semester_id, user_id) REFERENCES semesters(id, user_id) ON DELETE CASCADE
);
