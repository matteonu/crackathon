from ..db import get_db


def get_dashboard(user_id):
    """Everything the dashboard shows for one user."""
    conn = get_db()
    user = conn.execute(
        "SELECT username, birth_date, study_start FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    semesters = [dict(r) for r in conn.execute(
        "SELECT id, label, study_hours_per_week FROM semesters WHERE user_id = ? ORDER BY id",
        (user_id,),
    )]
    for semester in semesters:
        semester["courses"] = [dict(r) for r in conn.execute(
            """SELECT c.id, c.code, c.title, c.term, c.ects, c.professor, sc.desired_grade
               FROM semester_courses sc JOIN courses c ON c.id = sc.course_id
               WHERE sc.semester_id = ? ORDER BY c.code""",
            (semester["id"],),
        )]
        for course in semester["courses"]:
            course["resources"] = [dict(r) for r in conn.execute(
                "SELECT kind, title, url FROM course_resources WHERE course_id = ? ORDER BY id",
                (course["id"],),
            )]
    return {"user": dict(user), "semesters": semesters}
