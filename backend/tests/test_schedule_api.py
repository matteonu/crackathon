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
                          "dinner": ["18:00", "19:00"], "studyBlockSize": 60,
                          "studyHoursPerWeek": None, "alpha": .3, "beta": 5, "daysOff": [],
                          "studyDays": [0, 1, 2, 3, 4, 5, 6]})
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
        default = self.studied()
        self.prefs({"studyHoursPerWeek": 14})
        self.generate()
        self.assertLess(self.studied(), default)
        # A budget above what a week holds is the same as none.
        self.prefs({"studyHoursPerWeek": 168})
        self.generate()
        self.assertEqual(self.studied(), default)

    def test_with_no_budget_every_free_slot_is_used(self):
        self.add(1)
        self.generate(fromDate="2027-02-01")
        # 08:00-20:00 less lunch and dinner is 10 h, every day of the week planned.
        self.assertEqual(self.studied() / 60, 10 * 7)

    def test_the_day_window_and_block_size_reach_the_plan(self):
        self.add(1)
        self.prefs({"dayStart": "10:00", "dayEnd": "14:00", "lunch": ["12:00", "12:30"],
                    "dinner": ["13:45", "14:00"], "studyBlockSize": 30})
        self.generate()
        blocks = self.blocks()
        self.assertTrue(all("10:00" <= block["start"] and block["end"] <= "14:00" for block in blocks))
        # Learning is joined into sessions; a recall block is still one study block long.
        recall = [block for block in blocks if block["type"] == "recall"]
        self.assertTrue(recall)
        self.assertTrue(all(self.minutes(block) <= 30 for block in recall))

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
        # Alike in everything the scheduler weighs, so they come out close together.
        even = {entry["subjectId"]: entry["scheduledHours"] for entry in self.generate().get_json()["summary"]}
        self.assertAlmostEqual(even["course-1"], even["course-2"], delta=max(even.values()) / 3)
        self.patch({"priority": 1}, course_id=1)
        self.patch({"priority": 5}, course_id=2)
        summary = {entry["subjectId"]: entry["scheduledHours"]
                   for entry in self.generate().get_json()["summary"]}
        self.assertGreater(summary["course-1"], summary["course-2"])
        self.assertGreater(summary["course-1"], even["course-1"])

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


class TargetHoursTests(ScheduleApiCase):

    def test_generating_sets_what_each_course_asks_for(self):
        self.add(1)
        self.add(2)
        self.assertEqual([s["targetHours"] for s in self.plan()["subjects"]], [0, 0])
        plan = self.generate().get_json()
        targets = {s["id"]: s["targetHours"] for s in self.plan()["subjects"]}
        for entry in plan["summary"]:
            self.assertAlmostEqual(targets[entry["subjectId"]], entry["scheduledHours"], places=2)
        self.assertTrue(all(value > 0 for value in targets.values()))

    def test_the_target_adds_up_every_week_planned(self):
        self.add(1)
        self.generate(fromDate="2027-02-01")
        first = self.plan()["subjects"][0]["targetHours"]
        self.generate(fromDate="2027-02-08")
        both = self.plan()["subjects"][0]["targetHours"]
        self.assertGreater(both, first)
        self.assertAlmostEqual(both, self.studied() / 60, places=2)

    studied = PreferenceTests.studied
    minutes = GenerateTests.minutes

    def test_a_dry_run_changes_no_target(self):
        self.add(1)
        self.generate(dryRun=True)
        self.assertEqual(self.plan()["subjects"][0]["targetHours"], 0)


class SlotTests(ScheduleApiCase):
    """The user's own slots: drawn, moved, resized, deleted, and planned around."""

    def slot(self, user=ALICE, **body):
        return self.client.post("/api/semesters/2026W/plan/blocks", json=body, headers=user)

    def move(self, block_id, user=ALICE, **body):
        return self.client.patch(f"/api/semesters/2026W/plan/blocks/{block_id}", json=body, headers=user)

    def remove(self, block_id, user=ALICE):
        return self.client.delete(f"/api/semesters/2026W/plan/blocks/{block_id}", headers=user)

    def mine(self):
        return [b for b in self.blocks() if b["source"] == "manual"]

    def test_draw_a_course_slot_before_any_plan_exists(self):
        self.add(1)
        response = self.slot(date="2027-02-02", start="09:00", end="11:00", kind="course", courseId=1)
        self.assertEqual(response.status_code, 201)
        plan = self.plan()["plan"]
        self.assertIsNone(plan["generatedAt"])
        self.assertEqual([(b["start"], b["end"], b["subjectId"], b["type"]) for b in plan["blocks"]],
                         [("09:00", "11:00", "course-1", "active_learning")])
        self.assertEqual(self.plan()["subjects"][0]["targetHours"], 2)    # counts towards the target

    def test_a_break_is_a_slot_without_a_course(self):
        self.add(1)
        self.slot(date="2027-02-02", start="14:00", end="15:30", kind="break")
        (block,) = self.mine()
        self.assertEqual((block["type"], block["label"], block["subjectId"]), ("meal", "Break", None))

    def test_regenerating_keeps_my_slots_and_plans_around_them(self):
        self.add(1)
        self.generate()
        self.slot(date="2027-02-02", start="09:00", end="11:00", kind="break")
        self.slot(date="2027-02-03", start="13:00", end="14:00", kind="course", courseId=1)
        self.generate()
        self.assertEqual(len(self.mine()), 2)
        for date, start, end in (("2027-02-02", "09:00", "11:00"), ("2027-02-03", "13:00", "14:00")):
            others = [b for b in self.blocks() if b["date"] == date and b["source"] == "generated"
                      and b["type"] != "meal" and b["start"] < end and b["end"] > start]
            self.assertEqual(others, [], f"a generated slot sits on {date} {start}")

    def test_my_course_slots_count_against_its_cap(self):
        self.add(1)
        self.client.patch("/api/semesters/2026W/courses/1", json={"maxStudyHours": 5}, headers=ALICE)
        self.slot(date="2027-02-01", start="08:00", end="12:00", kind="course", courseId=1)
        self.generate()
        generated = sum(self.minutes(b) for b in self.blocks()
                        if b["source"] == "generated" and b["type"] == "active_learning") / 60
        self.assertLessEqual(generated, 1 + 1e-8)          # 5 h cap, 4 already mine

    def test_drawing_over_a_generated_slot_replaces_it(self):
        self.add(1)
        self.generate()
        target = next(b for b in self.blocks() if b["type"] == "active_learning")
        self.slot(date=target["date"], start=target["start"], end=target["end"], kind="break")
        self.assertNotIn(target["id"], [b["id"] for b in self.blocks()])

    def test_my_slots_cannot_overlap_each_other(self):
        self.add(1)
        self.slot(date="2027-02-02", start="09:00", end="11:00", kind="break")
        response = self.slot(date="2027-02-02", start="10:30", end="12:00", kind="course", courseId=1)
        self.assertEqual(response.status_code, 409)
        # Touching is fine.
        self.assertEqual(self.slot(date="2027-02-02", start="11:00", end="12:00", kind="break").status_code, 201)

    def test_moving_a_generated_slot_makes_it_mine(self):
        self.add(1)
        self.generate()
        block = next(b for b in self.blocks() if b["type"] == "active_learning")
        response = self.move(block["id"], date="2027-02-10", start="21:00", end="22:15")
        self.assertEqual(response.status_code, 200)
        moved = next(b for b in self.blocks() if b["id"] == block["id"])
        self.assertEqual((moved["date"], moved["start"], moved["end"], moved["source"]),
                         ("2027-02-10", "21:00", "22:15", "manual"))
        self.assertEqual(self.move(block["id"], end="22:45").status_code, 200)      # resize just the end
        self.assertEqual(next(b for b in self.blocks() if b["id"] == block["id"])["end"], "22:45")

    def test_deleting_a_slot(self):
        self.add(1)
        self.slot(date="2027-02-02", start="09:00", end="11:00", kind="course", courseId=1)
        (block,) = self.mine()
        self.assertEqual(self.remove(block["id"]).status_code, 200)
        self.assertIsNone(self.plan()["plan"])
        self.assertEqual(self.remove(block["id"]).status_code, 404)

    def test_bad_slots_are_refused(self):
        self.add(1)
        for bad in ({"date": "2027-02-02", "start": "09:00", "end": "11:00"},                 # no kind
                    {"date": "2027-02-02", "start": "11:00", "end": "09:00", "kind": "break"},
                    {"date": "2026-01-01", "start": "09:00", "end": "11:00", "kind": "break"},
                    {"date": "2027-02-02", "start": "9", "end": "11:00", "kind": "break"},
                    {"date": "2027-02-02", "start": "09:00", "end": "11:00", "kind": "course"},
                    {"date": "2027-02-02", "start": "09:00", "end": "11:00", "kind": "course", "courseId": 2}):
            self.assertEqual(self.slot(**bad).status_code, 400, bad)

    def test_another_user_cannot_touch_my_slots(self):
        self.add(1)
        self.slot(date="2027-02-02", start="09:00", end="11:00", kind="break")
        (block,) = self.mine()
        self.assertEqual(self.move(block["id"], user=BOB, start="10:00").status_code, 404)
        self.assertEqual(self.remove(block["id"], user=BOB).status_code, 404)
        self.assertEqual(len(self.mine()), 1)

    minutes = GenerateTests.minutes


class SessionTests(ScheduleApiCase):

    def test_back_to_back_blocks_of_a_course_are_one_slot(self):
        self.add(1)
        self.generate()
        by_day = {}
        for block in self.blocks():
            by_day.setdefault(block["date"], []).append(block)
        for date, blocks in by_day.items():
            blocks.sort(key=lambda b: b["start"])
            for a, b in zip(blocks, blocks[1:]):
                self.assertFalse(a["subjectId"] and a["subjectId"] == b["subjectId"] and a["type"] == b["type"]
                                 and a["end"] == b["start"], f"{date}: {a['start']}-{a['end']} and {b['start']}-{b['end']}")
        # Morning learning, 08:00 until lunch, is one session.
        first = sorted(by_day["2027-02-01"], key=lambda b: b["start"])[0]
        self.assertEqual((first["start"], first["end"], first["type"]), ("08:00", "12:00", "active_learning"))



class WeekTests(ScheduleApiCase):
    """A proposal covers the week open in the calendar, not the whole study phase."""

    def test_one_week_by_default(self):
        self.add(1)
        plan = self.generate().get_json()
        self.assertEqual({b["date"] for b in plan["blocks"]},
                         {f"2027-02-0{d}" for d in range(1, 8)})

    def test_an_explicit_week(self):
        self.add(1)
        plan = self.generate(fromDate="2027-01-04", toDate="2027-01-10").get_json()
        dates = {b["date"] for b in plan["blocks"]}
        self.assertEqual((min(dates), max(dates)), ("2027-01-04", "2027-01-10"))

    def test_a_week_past_the_phase_is_cut_at_its_end(self):
        self.add(1)
        plan = self.generate(fromDate="2027-02-12").get_json()
        self.assertEqual(max(b["date"] for b in plan["blocks"]), "2027-02-14")   # the phase's last day
        # No study on the exam day itself; lunch and dinner still happen.
        self.assertEqual(max(b["date"] for b in plan["blocks"] if b["type"] != "meal"), "2027-02-13")

    def test_planning_one_week_leaves_the_others_alone(self):
        self.add(1)
        self.generate(fromDate="2027-02-01")
        first = [b for b in self.blocks() if b["date"] <= "2027-02-07"]
        self.generate(fromDate="2027-02-08")
        self.assertEqual([b for b in self.blocks() if b["date"] <= "2027-02-07"], first)
        self.generate(fromDate="2027-02-01")      # and again: the second week survives
        self.assertTrue(any(b["date"] >= "2027-02-08" for b in self.blocks()))

    def test_bad_weeks_are_refused(self):
        self.add(1)
        for body in ({"toDate": "2027-01-31"}, {"toDate": "2027-03-01"}, {"toDate": "next week"}):
            self.assertEqual(self.generate(**body).status_code, 400, body)


class MealTests(ScheduleApiCase):
    """Lunch and dinner are slots in the calendar too."""

    def slot(self, **body):
        return self.client.post("/api/semesters/2026W/plan/blocks", json=body, headers=ALICE)

    def test_a_plan_holds_lunch_and_dinner(self):
        self.add(1)
        self.generate()
        meals = {(b["start"], b["end"], b["label"]) for b in self.blocks() if b["date"] == "2027-02-02" and b["type"] == "meal"}
        self.assertEqual(meals, {("12:00", "13:00", "Lunch"), ("18:00", "19:00", "Dinner")})

    def test_drawing_over_lunch_replaces_it_and_regenerating_respects_that(self):
        self.add(1)
        self.generate()
        self.slot(date="2027-02-02", start="12:00", end="13:00", kind="course", courseId=1)
        self.generate()
        lunch = [b for b in self.blocks() if b["date"] == "2027-02-02" and b["label"] == "Lunch"]
        self.assertEqual(lunch, [])
        self.assertTrue(any(b["label"] == "Lunch" for b in self.blocks() if b["date"] == "2027-02-03"))



class DayTests(ScheduleApiCase):
    """Study weekdays, one day at a time, clearing a day, and meals that stay removed."""

    def slots_on(self, date):
        return [b for b in self.blocks() if b["date"] == date]

    def remove(self, block_id):
        return self.client.delete(f"/api/semesters/2026W/plan/blocks/{block_id}", headers=ALICE)

    def clear(self, date, user=ALICE):
        return self.client.delete(f"/api/semesters/2026W/plan/days/{date}", headers=user)

    def test_only_the_chosen_weekdays_are_planned(self):
        self.add(1)
        self.assertEqual(self.prefs({"studyDays": [0, 1, 2, 3, 4]}).get_json()["studyDays"], [0, 1, 2, 3, 4])
        self.generate()                                   # Mon 1 Feb to Sun 7 Feb
        self.assertEqual(sorted({b["date"] for b in self.blocks()}), [f"2027-02-0{d}" for d in range(1, 6)])

    def test_bad_study_days_are_refused(self):
        for bad in ([], [7], [1, 1], "weekdays", [True]):
            self.assertEqual(self.prefs({"studyDays": bad}).status_code, 400, bad)

    def test_planning_one_day(self):
        self.add(1)
        self.generate()
        week = [b for b in self.blocks() if b["date"] != "2027-02-03"]
        self.generate(fromDate="2027-02-03", toDate="2027-02-03")
        self.assertEqual([b for b in self.blocks() if b["date"] != "2027-02-03"], week)   # the rest untouched
        self.assertTrue(self.slots_on("2027-02-03"))

    def test_one_day_is_planned_even_off_the_chosen_weekdays(self):
        self.add(1)
        self.prefs({"studyDays": [0, 1, 2, 3, 4]})
        self.generate(fromDate="2027-02-06", toDate="2027-02-06")      # a Saturday, asked for
        self.assertTrue(any(b["type"] != "meal" for b in self.slots_on("2027-02-06")))

    def test_a_removed_lunch_stays_removed(self):
        self.add(1)
        self.generate()
        lunch = next(b for b in self.slots_on("2027-02-02") if b["label"] == "Lunch")
        self.assertEqual(self.remove(lunch["id"]).status_code, 200)
        self.generate()
        self.assertFalse(any(b["label"] == "Lunch" for b in self.slots_on("2027-02-02")))
        self.assertTrue(any(b["label"] == "Lunch" for b in self.slots_on("2027-02-03")))

    def test_a_moved_dinner_is_not_doubled(self):
        self.add(1)
        self.generate()
        dinner = next(b for b in self.slots_on("2027-02-02") if b["label"] == "Dinner")
        self.client.patch(f"/api/semesters/2026W/plan/blocks/{dinner['id']}", json={"start": "19:00", "end": "20:00"},
                          headers=ALICE)
        self.generate()
        dinners = [(b["start"], b["source"]) for b in self.slots_on("2027-02-02") if b["label"] == "Dinner"]
        self.assertEqual(dinners, [("19:00", "manual")])

    def test_clearing_a_day_empties_it_and_starts_it_over(self):
        self.add(1)
        self.generate()
        self.client.post("/api/semesters/2026W/plan/blocks", headers=ALICE,
                         json={"date": "2027-02-02", "start": "21:00", "end": "22:00", "kind": "break"})
        lunch = next(b for b in self.slots_on("2027-02-02") if b["label"] == "Lunch")
        self.remove(lunch["id"])
        self.assertEqual(self.clear("2027-02-02").status_code, 200)
        self.assertEqual(self.slots_on("2027-02-02"), [])            # yours and generated alike
        self.assertTrue(self.slots_on("2027-02-03"))
        self.generate(fromDate="2027-02-02", toDate="2027-02-02")
        self.assertTrue(any(b["label"] == "Lunch" for b in self.slots_on("2027-02-02")))   # meals come back

    def test_clearing_needs_a_day_in_the_phase(self):
        self.add(1)
        self.assertEqual(self.clear("2026-01-01").status_code, 400)
        self.assertEqual(self.clear("2027-02-02", user=BOB).status_code, 404)
