"""The study-phase scheduler: a JSON request in, a week-by-week plan out.

Pure Python with no Flask, no database and no network, so it can be run from a test or from
the command line. `backend/planner.py` builds the request from the caller's semester and
stores the blocks that come back.

    from schedule_planner.main import generate_schedule

Nothing is re-exported here on purpose: importing `.main` from this file makes
`python -m schedule_planner.main` warn on stderr, where the CLI puts its errors.
"""
