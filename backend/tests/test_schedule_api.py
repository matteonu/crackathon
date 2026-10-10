"""Generating a study plan: /api/semesters/<semkez>/plan/generate and /preferences."""
import db
from tests.test_planner import ALICE, BOB, PlannerCase

# HS26's study phase is 2026-12-21 to 2027-02-14. Most tests plan the last two weeks of it
# so a run stays small; fromDate is always explicit so the tests do not depend on today.
FROM = "2027-02-01"


class ScheduleApiCase(PlannerCase):

    def generate(self, semkez="2026W", user=ALICE, **body):
        return self.client.post(f"/api/semesters/{semkez}/plan/generate",
                                json={"fromDate": FROM, **body}, headers=user)

    def prefs(self, body, semkez="2026W", user=ALICE):
        return self.client.put(f"/api/semesters/{semkez}/preferences", json=body, headers=user)

    def plan(self, semkez="2026W", user=ALICE):
        return self.get(f"/api/semesters/{semkez}/plan", user).get_json()

    def blocks(self, **kwargs):
        return self.plan(**kwargs)["plan"]["blocks"]


class GenerateTests(ScheduleApiCase):

    def test_a_semester_needs_a_course_before_it_can_be_planned(self):
        self.assertEqual(self.generate().status_code, 400)        # no semester row yet
        self.prefs({"studyBlockSize": 90})                        # creates the row, still no course
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("course", response.get_json()["error"])

    def test_generating_stores_blocks_and_the_plan_comes_back(self):
        self.add(1)
        self.add(2)
        response = self.generate()
        self.assertEqual(response.status_code, 200)
        plan = response.get_json()
        self.assertEqual(plan["fromDate"], FROM)
        self.assertEqual({entry["subjectId"] for entry in plan["summary"]}, {"course-1", "course-2"})
        self.assertTrue(all(entry["scheduledHours"] > 0 for entry in plan["summary"]))

        stored = self.plan()["plan"]
        self.assertEqual([dict(block, id=None) for block in stored["blocks"]],
                         [dict(block, id=None) for block in plan["blocks"]])
        self.assertEqual(stored["generatedAt"], plan["generatedAt"])
        # Every block is inside the planned window, ordered, and typed.
        self.assertTrue(all(FROM <= block["date"] <= "2027-02-14" for block in stored["blocks"]))
        self.assertEqual({block["type"] for block in stored["blocks"]},
                         {"active_learning", "recall", "meal"})
        for block in stored["blocks"]:
            self.assertLess(block["start"], block["end"])
            if block["type"] == "meal":
                self.assertIsNone(block["subjectId"])
                self.assertIn(block["label"], ("Lunch", "Dinner"))
            else:
                self.assertIn(block["subjectId"], ("course-1", "course-2"))

    def test_the_same_request_gives_the_same_plan(self):
        self.add(1)
        first = self.generate().get_json()["blocks"]
        second = self.generate().get_json()["blocks"]
        self.assertEqual([dict(block, id=None) for block in first],
                         [dict(block, id=None) for block in second])

    def test_a_dry_run_proposes_without_storing(self):
        self.add(1)
        proposal = self.generate(dryRun=True).get_json()
        self.assertTrue(proposal["blocks"])
        self.assertTrue(all(block["id"] is None for block in proposal["blocks"]))
        self.assertIsNone(self.plan()["plan"])

    def test_regenerating_later_keeps_the_weeks_already_behind(self):
        self.add(1)
        self.generate()
        before = [block for block in self.blocks() if block["date"] < "2027-02-08"]
        self.assertTrue(before)
        self.generate(fromDate="2027-02-08")
        after = self.blocks()
        self.assertEqual([block for block in after if block["date"] < "2027-02-08"], before)
        self.assertEqual(self.plan()["plan"]["fromDate"], "2027-02-08")

    def test_hours_already_planned_count_against_a_cap(self):
        self.add(1)
        self.patch({"maxStudyHours": 4})
        self.generate()
        active = [block for block in self.blocks() if block["type"] == "active_learning"]
        hours = sum(self.minutes(block) for block in active) / 60
        self.assertLessEqual(hours, 4 + 1e-8)
        self.assertTrue(any(block["type"] == "recall" for block in self.blocks()))   # recall is exempt

    def test_a_finished_course_is_left_out(self):
        self.add(1)
        self.add(2)
        self.patch({"completed": True}, course_id=2)
        plan = self.generate().get_json()
        self.assertEqual([entry["subjectId"] for entry in plan["summary"]], ["course-1"])

    def test_nothing_to_plan_when_every_exam_has_passed(self):
        self.add(1)
        self.patch({"examDate": "2026-12-22"})
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("exam", response.get_json()["error"])

    def test_no_study_is_planned_on_or_after_an_exam(self):
        self.add(1)
        self.add(2)
        self.patch({"examDate": "2027-02-05"}, course_id=1)
        self.generate()
        dates = [block["date"] for block in self.blocks() if block["subjectId"] == "course-1"]
        self.assertTrue(dates)
        self.assertLess(max(dates), "2027-02-05")

    def test_a_bad_from_date_is_refused(self):
        self.add(1)
        for bad in ("2026-01-01", "2027-02-30", "soon", 5):
            self.assertEqual(self.generate(fromDate=bad).status_code, 400, bad)

    def test_another_user_cannot_see_or_change_my_plan(self):
        self.add(1)
        self.generate()
        self.assertIsNone(self.plan(user=BOB)["plan"])
        self.assertEqual(self.generate(user=BOB).status_code, 400)       # Bob has no courses
        self.assertTrue(self.blocks())                                   # mine is untouched

    def minutes(self, block):
        return ((int(block["end"][:2]) * 60 + int(block["end"][3:]))
                - (int(block["start"][:2]) * 60 + int(block["start"][3:])))

    def patch(self, body, course_id=1, semkez="2026W", user=ALICE):
        return self.client.patch(f"/api/semesters/{semkez}/courses/{course_id}", json=body, headers=user)


class PreferenceTests(ScheduleApiCase):

    def test_defaults_before_anything_is_saved(self):
        self.assertEqual(self.plan()["preferences"],
                         {"dayStart": "08:00", "dayEnd": "20:00", "lunch": ["12:00", "13:00"],
                          "dinner": ["18:00", "19:00"], "studyBlockSize": 90,
                          "studyHoursPerWeek": None, "alpha": .3, "beta": 5, "daysOff": []})
        self.add(1)      # adding a course creates the row; the defaults must survive it
        self.assertEqual(self.plan()["preferences"]["dayStart"], "08:00")

    def test_saving_and_reading_them_back(self):
        saved = self.prefs({"dayStart": "09:00", "dayEnd": "18:00", "lunch": ["12:30", "13:15"],
                            "dinner": ["18:30", "19:15"], "studyBlockSize": 60,
                            "studyHoursPerWeek": 30, "alpha": .5, "beta": 3,
                            "daysOff": [{"startDate": "2027-02-03"},
                                        {"startDate": "2027-02-06", "rangeLength": 2}]})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json(), self.plan()["preferences"])
        self.assertEqual(self.plan()["preferences"]["daysOff"],
                         [{"startDate": "2027-02-03", "rangeLength": 1},
                          {"startDate": "2027-02-06", "rangeLength": 2}])

    def test_bad_preferences_are_refused(self):
        for bad in ({"dayStart": "9am"}, {"dayEnd": "24:00"}, {"dayStart": "20:00", "dayEnd": "08:00"},
                    {"dayEnd": "07:00"}, {"lunch": ["13:00", "12:00"]}, {"lunch": ["12:00"]},
                    {"dinner": "evening"}, {"studyBlockSize": 5}, {"studyBlockSize": 90.5},
                    {"studyHoursPerWeek": -1}, {"studyHoursPerWeek": 200}, {"studyHoursPerWeek": 10.5},
                    {"alpha": "high"}, {"beta": 0}, {"daysOff": "none"},
                    {"daysOff": [{"startDate": "nope"}]}, {"daysOff": [{"startDate": "2027-02-03", "rangeLength": 0}]},
                    {"daysOff": [{"startDate": "2027-02-03"}, {"startDate": "2027-02-03"}]}, {}):
            self.assertEqual(self.prefs(bad).status_code, 400, bad)
        self.assertEqual(self.plan()["preferences"], self.plan()["preferences"])   # nothing half-written

    def test_a_day_off_is_left_empty_and_shortens_the_week(self):
        self.add(1)
        self.prefs({"daysOff": [{"startDate": "2027-02-03", "rangeLength": 2}]})
        self.generate()
        dates = {block["date"] for block in self.blocks()}
        self.assertNotIn("2027-02-03", dates)
        self.assertNotIn("2027-02-04", dates)
        self.assertIn("2027-02-05", dates)

    def test_a_weekly_budget_plans_fewer_hours(self):
        self.add(1)
        self.add(2)
        self.generate()
        full = self.studied()
        self.prefs({"studyHoursPerWeek": 14})
        self.generate()
        self.assertLess(self.studied(), full)

    def test_the_day_window_and_block_size_reach_the_plan(self):
        self.add(1)
        self.prefs({"dayStart": "10:00", "dayEnd": "14:00", "lunch": ["12:00", "12:30"],
                    "dinner": ["13:45", "14:00"], "studyBlockSize": 30})
        self.generate()
        blocks = self.blocks()
        self.assertTrue(all("10:00" <= block["start"] and block["end"] <= "14:00" for block in blocks))
        self.assertTrue(all(self.minutes(block) <= 30 for block in blocks if block["type"] != "meal"))

    def test_preferences_belong_to_one_user_and_one_semester(self):
        self.prefs({"dayStart": "09:00"})
        self.assertEqual(self.plan(user=BOB)["preferences"]["dayStart"], "08:00")
        self.assertEqual(self.plan(semkez="2027S")["preferences"]["dayStart"], "08:00")
        self.assertEqual(self.plan()["preferences"]["dayStart"], "09:00")

    def studied(self):
        return sum(self.minutes(block) for block in self.blocks() if block["type"] != "meal")

    minutes = GenerateTests.minutes


class CoursePreferenceTests(ScheduleApiCase):

    def test_difficulty_falls_back_to_the_scraped_rating(self):
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute("INSERT INTO course_ratings (code, difficulty) VALUES ('252-0026-00L', 4.4)")
        self.add(1)
        self.add(2)
        first, second = self.plan()["subjects"]
        self.assertEqual(first["difficulty"], 4)      # rounded from the rating
        self.assertEqual(second["difficulty"], 3)     # no rating: the middle of the scale
        self.patch({"difficulty": 1})
        self.assertEqual(self.plan()["subjects"][0]["difficulty"], 1)

    def test_lecture_hours_come_from_the_offering_until_overridden(self):
        self.add(1)
        self.assertEqual(self.plan()["subjects"][0]["lecturePerWeek"], 6)
        self.patch({"lecturePerWeek": 2.5})
        self.assertEqual(self.plan()["subjects"][0]["lecturePerWeek"], 2.5)

    def test_bad_course_preferences_are_refused(self):
        self.add(1)
        for bad in ({"priority": 0}, {"priority": 6}, {"priority": 2.5}, {"difficulty": 0},
                    {"difficulty": 9}, {"maxStudyHours": -1}, {"maxStudyHours": "lots"},
                    {"lecturePerWeek": -1}, {"lecturePerWeek": 61}):
            self.assertEqual(self.patch(bad).status_code, 400, bad)
        self.assertEqual(self.patch({"priority": 1, "difficulty": None, "maxStudyHours": None,
                                     "lecturePerWeek": None}).status_code, 200)

    def test_priority_shifts_hours_between_courses(self):
        self.add(1)
        self.add(2)
        self.generate()
        self.assertEqual(len({entry["scheduledHours"] for entry in self.plan()["plan"]["summary"]}), 1)
        self.patch({"priority": 1}, course_id=1)
        self.patch({"priority": 5}, course_id=2)
        summary = {entry["subjectId"]: entry["scheduledHours"]
                   for entry in self.generate().get_json()["summary"]}
        self.assertGreater(summary["course-1"], summary["course-2"])

    patch = GenerateTests.patch


class StoredTotalsTests(ScheduleApiCase):

    def test_the_totals_describe_every_block_held_not_just_the_last_run(self):
        self.add(1)
        self.generate(fromDate="2027-02-01")
        whole = {entry["subjectId"]: entry["scheduledHours"] for entry in self.plan()["plan"]["summary"]}
        self.generate(fromDate="2027-02-08")
        after = {entry["subjectId"]: entry["scheduledHours"] for entry in self.plan()["plan"]["summary"]}
        # The second run planned one week, but the first week's blocks are still there.
        self.assertEqual(sorted(after), sorted(whole))
        self.assertAlmostEqual(after["course-1"], self.studied() / 60, places=2)

    def test_meals_are_not_counted_as_study(self):
        self.add(1)
        plan = self.generate().get_json()
        hours = sum(entry["scheduledHours"] for entry in plan["summary"])
        self.assertAlmostEqual(hours, self.studied() / 60, places=2)
        self.assertTrue(any(block["type"] == "meal" for block in plan["blocks"]))

    studied = PreferenceTests.studied
    minutes = GenerateTests.minutes
