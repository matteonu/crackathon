"""Marking a planned day fulfilled records its study totals without changing its slots."""
import db
from tests.test_planner import ALICE, BOB
from tests.test_schedule_api import FROM, ScheduleApiCase


class FulfillDayTests(ScheduleApiCase):
    def fulfill(self, date=FROM, user=ALICE, semkez="2026W"):
        return self.client.put(f"/api/semesters/{semkez}/plan/days/{date}/fulfill", json={}, headers=user)

    def record(self, course, hours, date=FROM):
        response = self.client.put(f"/api/semesters/2026W/courses/{course}/hours/{date}",
                                   json={"hours": hours}, headers=ALICE)
        self.assertEqual(response.status_code, 200)

    def records(self):
        return {subject["courseId"]: subject["hours"] for subject in self.plan()["subjects"]}

    def prepare(self):
        for course in (1, 2, 4):
            self.add(course)
        with self.app.app_context():
            conn = db.get_db()
            self.sid = conn.execute("SELECT id FROM semesters").fetchone()[0]
            with conn:
                conn.executemany("""INSERT INTO plan_blocks
                                    (semester_id, course_id, date, start_time, end_time, type, label, source)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", [
                    (self.sid, 1, FROM, "08:00", "09:30", "active_learning", None, "generated"),
                    (self.sid, 1, FROM, "10:00", "11:00", "active_learning", None, "manual"),
                    (self.sid, 1, FROM, "11:00", "11:30", "recall", None, "generated"),
                    (self.sid, None, FROM, "12:00", "13:00", "meal", "Lunch", "generated"),
                    (self.sid, 2, FROM, "13:00", "15:00", "active_learning", None, "generated"),
                    (self.sid, None, FROM, "15:00", "16:00", "meal", "Break", "manual"),
                ])

    def test_records_planned_totals_and_keeps_unrelated_records_and_all_slots(self):
        self.prepare()
        self.record(1, 1.25)
        self.record(2, 1)
        self.record(4, .75)
        self.record(1, 4, "2027-02-02")
        before = self.blocks()
        response = self.fulfill()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"date": FROM, "hours": [
            {"subjectId": "course-1", "hours": 3}, {"subjectId": "course-2", "hours": 2}]})
        self.assertEqual(self.records(), {1: {FROM: 3, "2027-02-02": 4}, 2: {FROM: 2}, 4: {FROM: .75}})
        self.assertEqual(self.blocks(), before)

    def test_repeating_fulfillment_replaces_hours_instead_of_adding_them(self):
        self.prepare()
        # Updating course 1 separately would temporarily exceed 24 hours. The entire
        # day's final replacement is valid and must be saved together.
        self.record(1, 0)
        self.record(2, 24)
        self.assertEqual(self.fulfill().status_code, 200)
        first = self.records()
        self.assertEqual(first, {1: {FROM: 3}, 2: {FROM: 2}, 4: {}})
        self.assertEqual(self.fulfill().status_code, 200)
        self.assertEqual(self.records(), first)

    def test_a_day_over_24_hours_is_rejected_without_any_partial_records(self):
        self.prepare()
        self.record(1, .5)
        self.record(2, .5)
        self.record(4, 23)
        before = self.records()
        slots = self.blocks()
        response = self.fulfill()
        self.assertEqual(response.status_code, 400)
        self.assertIn("24 hours", response.get_json()["error"])
        self.assertEqual(self.records(), before)
        self.assertEqual(self.blocks(), slots)

    def test_fractional_hours_are_summed_before_rounding(self):
        self.prepare()
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute("UPDATE plan_blocks SET end_time = '09:25' WHERE semester_id = ? AND start_time = '08:00'",
                             (self.sid,))
        self.assertEqual(self.fulfill().status_code, 200)
        self.assertEqual(self.records()[1], {FROM: 2.92})

    def test_empty_or_break_only_days_are_rejected_and_existing_hours_survive(self):
        self.prepare()
        self.record(1, 2, "2027-02-02")
        self.client.post("/api/semesters/2026W/plan/blocks", headers=ALICE,
                         json={"date": "2027-02-03", "start": "12:00", "end": "13:00", "kind": "break"})
        before = self.records()
        for date in ("2027-02-02", "2027-02-03"):
            self.assertEqual(self.fulfill(date).status_code, 400)
        self.assertEqual(self.records(), before)

    def test_invalid_dates_and_other_users_cannot_change_my_records(self):
        self.prepare()
        self.record(1, 1)
        before = self.records()
        for date in ("2026-01-01", "2027-02-30", "tomorrow"):
            self.assertEqual(self.fulfill(date).status_code, 400)
        self.assertEqual(self.fulfill(user=BOB).status_code, 404)
        self.add(1, user=BOB)
        self.assertEqual(self.fulfill(user=BOB).status_code, 400)  # Bob's own plan has no slots.
        self.assertEqual(self.records(), before)
        self.assertEqual(self.plan(user=BOB)["subjects"][0]["hours"], {})

    def test_saved_study_for_a_completed_course_can_still_be_fulfilled(self):
        self.prepare()
        self.client.patch("/api/semesters/2026W/courses/1", headers=ALICE, json={"completed": True})
        self.assertEqual(self.fulfill().status_code, 200)
        self.assertEqual(self.records()[1], {FROM: 3})
