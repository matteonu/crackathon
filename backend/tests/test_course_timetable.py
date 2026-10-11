import datetime as dt

import db
from course_timetable import teaching_period
from tests.test_planner import ALICE, BOB, PlannerCase


class CourseTimetableTests(PlannerCase):
    def slot(self, offering=900, **patch):
        values = dict(offering_id=offering, lecture_number='test V', weekday=0, date=None,
                      start_time='09:00', end_time='10:00', building='HG', floor='E', room='1',
                      first_half_semester=0, second_half_semester=0, biweekly=0, inherited_from=None)
        values.update(patch)
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute(f"INSERT INTO course_timeslots ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))

    def plan(self, user=ALICE, semester='2026W'):
        return self.get(f'/api/semesters/{semester}/plan', user).get_json()

    def test_only_own_courses_and_selected_semester_appear_before_learning_phase(self):
        self.add(1)
        self.slot()
        self.slot(901)
        self.slot(902)
        data = self.plan()
        events = data['timetable']['events']
        self.assertEqual(len(events), 14)
        self.assertEqual({event['subjectId'] for event in events}, {'course-1'})
        self.assertEqual(events[0]['date'], '2026-09-14')
        self.assertTrue(all(event['date'] < data['start'] for event in events))
        self.assertEqual(self.plan(BOB)['timetable']['events'], [])
        self.assertIsNone(data['plan'])  # Reading course times creates no study blocks.

    def test_one_off_dates_invalid_times_and_inherited_dated_slots(self):
        self.add(1)
        self.slot(date='7.10.', weekday=0)
        self.slot(date='2026-10-08', weekday=0)
        self.slot(date='2026-12-21')
        self.slot(date='31.2')
        self.slot(start_time='25:00')
        self.slot(date='7.10', inherited_from='2025W')
        self.assertEqual([e['date'] for e in self.plan()['timetable']['events']], ['2026-10-07','2026-10-08'])

    def test_half_semesters_biweekly_and_parallel_rooms(self):
        self.add(1)
        self.slot(first_half_semester=1, biweekly=1, inherited_from='2025W')
        self.slot(first_half_semester=1, biweekly=1, inherited_from='2025W', room='2')
        events = self.plan()['timetable']['events']
        self.assertEqual([e['date'] for e in events], ['2026-09-14','2026-09-28','2026-10-12','2026-10-26'])
        self.assertEqual(events[0]['rooms'], ['HG E 1','HG E 2'])
        self.assertEqual(events[0]['inheritedFrom'], '2025W')
        self.assertTrue(events[0]['biweekly'])
        self.slot(second_half_semester=1, start_time='11:00', end_time='12:00')
        second = [e for e in self.plan()['timetable']['events'] if e['start']=='11:00']
        self.assertEqual(len(second),7)
        self.assertEqual(second[0]['date'],'2026-11-02')

    def test_spring_timetable_skips_easter_week_and_ends_before_learning_phase(self):
        self.add(3, semkez='2027S')
        self.slot(902)
        data = self.plan(semester='2027S')
        events = data['timetable']['events']
        self.assertEqual(len(events),14)
        self.assertNotIn('2027-03-29',[event['date'] for event in events])
        self.assertTrue(all(event['date'] < '2027-06-01' for event in events))
        self.assertEqual(teaching_period('2026W'), (dt.date(2026,9,14),dt.date(2026,12,20)))
