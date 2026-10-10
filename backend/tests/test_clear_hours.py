"""Clearing recorded hours is scoped to one user's displayed week and keeps the study plan."""
import db
from tests.test_planner import ALICE, BOB
from tests.test_schedule_api import FROM, ScheduleApiCase


class ClearHoursTests(ScheduleApiCase):
    def clear(self, semkez="2026W", user=ALICE, date=FROM):
        return self.client.delete(f"/api/semesters/{semkez}/hours/weeks/{date}", headers=user)

    def record(self, course, date, hours, semkez="2026W", user=ALICE):
        response = self.client.put(f"/api/semesters/{semkez}/courses/{course}/hours/{date}",
                                   json={"hours": hours}, headers=user)
        self.assertEqual(response.status_code, 200)

    def test_clears_week_including_zero_and_completed_courses_but_keeps_other_dates_and_plan(self):
        for course in (1, 2, 4):
            self.add(course)
        self.record(1, "2027-02-02", 2)
        self.record(1, FROM, 3)
        self.record(2, "2027-02-03", 0)
        self.record(4, "2027-02-07", 1.5)
        self.record(1, "2027-01-31", 1)
        self.record(1, "2027-02-08", 4)
        self.record(4, "2027-02-14", 5)
        self.client.patch("/api/semesters/2026W/courses/2", json={"completed": True}, headers=ALICE)
        self.prefs({"studyHoursPerWeek": 14})
        custom = self.client.post("/api/semesters/2026W/plan/blocks", headers=ALICE,
                                 json={"date": FROM, "start": "08:00", "end": "10:00",
                                       "kind": "course", "courseId": 1})
        self.assertEqual(custom.status_code, 201)
        self.assertEqual(self.generate(toDate=FROM).status_code, 200)
        before = self.plan()
        response = self.clear()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"cleared": 4})
        expected = {**before, "subjects": [{**subject, "hours": {
            date: hours for date, hours in subject["hours"].items() if not FROM <= date <= "2027-02-07"
        }} for subject in before["subjects"]]}
        self.assertEqual(self.plan(), expected)  # Also keeps slots, sessions, targets and preferences.
        self.assertEqual(self.clear().get_json(), {"cleared": 0})
        self.assertEqual(self.plan(), expected)

    def test_keeps_other_users_and_other_semesters_hours(self):
        self.add(2)
        self.add(2, "2027S")
        self.add(2, user=BOB)
        self.record(2, FROM, 2)
        self.record(2, "2027-06-03", 3, semkez="2027S")
        self.record(2, FROM, 4, user=BOB)
        other_semester = self.plan(semkez="2027S")
        other_user = self.plan(user=BOB)
        self.assertEqual(self.clear().get_json(), {"cleared": 1})
        self.assertEqual(self.plan()["subjects"][0]["hours"], {})
        self.assertEqual(self.plan(semkez="2027S"), other_semester)
        self.assertEqual(self.plan(user=BOB), other_user)

    def test_empty_semester_is_a_noop_and_invalid_or_unauthenticated_requests_cannot_clear(self):
        self.assertEqual(self.clear().get_json(), {"cleared": 0})
        self.add(1)
        self.record(1, FROM, 2)
        before = self.plan()
        self.assertEqual(self.clear(user=BOB).get_json(), {"cleared": 0})
        self.assertEqual(self.client.delete(f"/api/semesters/2026W/hours/weeks/{FROM}").status_code, 401)
        for semkez in ("nonsense", "2019W"):
            self.assertEqual(self.clear(semkez).status_code, 400)
        for date in ("tomorrow", "2027-02-30", "2027-02-02", "2026-12-14", "2027-02-15", "9999-12-27"):
            self.assertEqual(self.clear(date=date).status_code, 400, date)
        self.assertEqual(self.plan(), before)

    def test_partial_week_at_phase_start_clears_only_that_weeks_records(self):
        self.add(2, "2027S")  # Starts Tuesday 1 June; the shown week starts Monday 31 May.
        self.record(2, "2027-06-01", 2, semkez="2027S")
        self.record(2, "2027-06-06", 3, semkez="2027S")
        self.record(2, "2027-06-07", 4, semkez="2027S")
        self.assertEqual(self.clear(semkez="2027S", date="2027-05-31").get_json(), {"cleared": 2})
        self.assertEqual(self.plan(semkez="2027S")["subjects"][0]["hours"], {"2027-06-07": 4})

    def test_old_semester_hours_can_be_cleared_after_the_catalogue_drops_it(self):
        self.add(1)
        self.record(1, FROM, 2)
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute("DELETE FROM course_offerings WHERE semkez = '2026W'")
        self.assertEqual(self.clear().get_json(), {"cleared": 1})
        self.assertEqual(self.plan()["subjects"][0]["hours"], {})
