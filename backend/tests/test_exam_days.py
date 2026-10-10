"""Exam-day preferences apply to weekly and selected-day generation."""
from tests.test_planner import ALICE
from tests.test_schedule_api import FROM, ScheduleApiCase


class ExamDayTests(ScheduleApiCase):
    def test_disabling_exam_days_off_plans_around_exam_times_in_weekly_and_day_generation(self):
        self.add(1)
        self.add(2)
        self.assertEqual(self.prefs({"examDaysOff": False}).status_code, 200)
        for completed in (False, True):
            with self.subTest(completed=completed):
                response = self.client.patch("/api/semesters/2026W/courses/1", headers=ALICE,
                                             json={"examDate": "2027-02-03", "examStart": "09:00",
                                                   "examEnd": "11:00", "completed": completed})
                self.assertEqual(response.status_code, 200)
                weekly = self.generate(toDate="2027-02-07", dryRun=True)
                self.assertEqual(weekly.status_code, 200)
                day = [block for block in weekly.get_json()["blocks"] if block["date"] == "2027-02-03"]
                self.assertTrue(any(block["subjectId"] == "course-2" for block in day))
                self.assertFalse(any(block["subjectId"] == "course-1" for block in day))
                for block in day:
                    self.assertTrue(block["end"] <= "09:00" or block["start"] >= "11:00", block)
                daily = self.generate(toDate="2027-02-07", onlyDate="2027-02-03", dryRun=True)
                self.assertEqual(daily.status_code, 200)
                self.assertEqual(daily.get_json()["blocks"], day)
        self.prefs({"examDaysOff": True})
        self.assertEqual(self.generate(toDate="2027-02-07").status_code, 200)
        self.assertFalse(any(block["date"] == "2027-02-03" for block in self.blocks()))

    def test_disabled_option_allows_unknown_exam_time_but_respects_explicit_days_off(self):
        self.add(1)
        self.add(2)
        self.client.patch("/api/semesters/2026W/courses/1", headers=ALICE,
                          json={"examDate": "2027-02-03"})
        self.prefs({"examDaysOff": False})
        self.assertEqual(self.generate(toDate="2027-02-07").status_code, 200)
        self.assertTrue(any(block["date"] == "2027-02-03" and block["subjectId"] == "course-2"
                            for block in self.blocks()))
        self.prefs({"daysOff": [{"startDate": "2027-02-03"}]})
        self.assertEqual(self.generate(toDate="2027-02-07").status_code, 200)
        self.assertFalse(any(block["date"] == "2027-02-03" for block in self.blocks()))

    def test_exam_day_is_free_for_all_courses_in_weekly_and_day_generation(self):
        self.add(1)
        self.add(2)
        self.assertEqual(self.generate(toDate="2027-02-07").status_code, 200)
        response = self.client.patch("/api/semesters/2026W/courses/1", headers=ALICE,
                                     json={"examDate": "2027-02-03", "examStart": "09:00", "examEnd": "11:00"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.generate(toDate="2027-02-07", onlyDate="2027-02-03").status_code, 200)
        self.assertFalse(any(block["date"] == "2027-02-03" for block in self.blocks()))
        self.assertEqual(self.generate(toDate="2027-02-07").status_code, 200)
        self.assertFalse(any(block["date"] == "2027-02-03" for block in self.blocks()))
        self.assertTrue(any(block["date"] == FROM and block["subjectId"] for block in self.blocks()))

    def test_completed_courses_exam_day_remains_free_and_custom_slots_are_preserved(self):
        self.add(1)
        self.add(2)
        self.client.patch("/api/semesters/2026W/courses/1", headers=ALICE,
                          json={"examDate": "2027-02-03", "completed": True})
        response = self.client.post("/api/semesters/2026W/plan/blocks", headers=ALICE,
                                    json={"date": "2027-02-03", "start": "08:30", "end": "11:30",
                                          "kind": "course", "courseId": 2})
        self.assertEqual(response.status_code, 201)
        before = [block for block in self.blocks() if block["date"] == "2027-02-03"]
        self.assertEqual(self.generate(toDate="2027-02-07").status_code, 200)
        self.assertEqual([block for block in self.blocks() if block["date"] == "2027-02-03"], before)
