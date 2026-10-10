"""Busy time: slots the user already filled, which the scheduler plans around."""
import copy
import json
from pathlib import Path
import unittest

from schedule_planner.main import generate_schedule

M = lambda t: int(t[:2]) * 60 + int(t[3:])


class BusyTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(Path(__file__).with_name('example_input.json').read_text())

    def day(self, plan, date):
        return next(d for w in plan['weeks'] for d in w['days'] if d['date'] == date)

    def test_no_busy_time_changes_nothing(self):
        self.assertEqual(generate_schedule(self.data), generate_schedule(dict(self.data, busy=[])))

    def test_nothing_is_planned_on_busy_time(self):
        busy = [{'date': '2026-11-02', 'start_time': '09:00', 'end_time': '11:15'},
                {'date': '2026-11-02', 'start_time': '15:00', 'end_time': '16:00', 'subject': 'Geometry'}]
        plan = generate_schedule(dict(self.data, busy=busy))
        for block in self.day(plan, '2026-11-02')['blocks']:
            for entry in busy:
                self.assertFalse(M(block['start_time']) < M(entry['end_time'])
                                 and M(block['end_time']) > M(entry['start_time']), block)
        # Fragments shorter than the configured block size stay unused.
        blocks = self.day(plan, '2026-11-02')['blocks']
        self.assertNotIn('11:15', [b['start_time'] for b in blocks])
        self.assertTrue(all(b['duration_minutes'] >= self.data['study_block_size']
                            for b in blocks if b['type'] != 'meal'))

    def small_plan(self, **options):
        subject = dict(ects=7, lecture_per_week=0, difficulty=3, priority=3, examdate='2026-11-20')
        return dict(subjects={'Probability theory': dict(subject), 'Probabilistic AI': dict(subject)},
                    exam_session={'start_date': '2026-11-02', 'range_length': 1},
                    day_start='08:00', day_end='20:00', lunch_time=['12:00', '13:00'],
                    dinner_time=['18:00', '19:00'], study_block_size=60, **options)

    def test_custom_study_absorbs_fragments_and_reduces_its_remaining_allocation(self):
        data = self.small_plan(busy=[{'date': '2026-11-02', 'start_time': '08:30',
                                     'end_time': '11:30', 'subject': 'Probability theory'}])
        original = copy.deepcopy(data)
        plan = generate_schedule(data)
        self.assertEqual(data, original)
        self.assertEqual(plan['busy_adjustments'], [{'index': 0, 'start_time': '08:00', 'end_time': '12:00'}])
        week = plan['weeks'][0]
        self.assertAlmostEqual(sum(week['target_hours_per_subject'].values()), 10)
        self.assertLess(week['scheduled_hours_per_subject']['Probability theory'],
                        week['scheduled_hours_per_subject']['Probabilistic AI'])
        for block in self.day(plan, '2026-11-02')['blocks']:
            if block['type'] != 'meal':
                self.assertGreaterEqual(block['duration_minutes'], 60)
                self.assertGreaterEqual(block['start_time'], '12:00')

    def test_custom_study_and_generated_blocks_share_the_weekly_budget(self):
        data = self.small_plan(study_hours_per_week=35, busy=[{
            'date': '2026-11-02', 'start_time': '08:30', 'end_time': '11:30', 'subject': 'Probability theory'}])
        plan = generate_schedule(data)
        week = plan['weeks'][0]
        self.assertEqual(week['budget_hours'], 5)
        self.assertAlmostEqual(sum(week['target_hours_per_subject'].values()), 5)
        self.assertEqual(sum(week['scheduled_hours_per_subject'].values()), 1)
        self.assertEqual(week['scheduled_hours_per_subject']['Probability theory'], 0)
        data['study_hours_per_week'] = 14       # 2 hours for this one-day request; already 3 custom hours
        plan = generate_schedule(data)
        self.assertEqual(plan['busy_adjustments'], [])
        self.assertEqual(sum(plan['summary']['scheduled_hours_per_subject'].values()), 0)

    def test_extensions_respect_meals_other_custom_slots_and_subject_caps(self):
        data = self.small_plan(busy=[
            {'date': '2026-11-02', 'start_time': '08:00', 'end_time': '08:15'},
            {'date': '2026-11-02', 'start_time': '08:30', 'end_time': '11:30', 'subject': 'Probability theory'},
            {'date': '2026-11-02', 'start_time': '11:45', 'end_time': '12:00', 'subject': 'Probabilistic AI'}])
        plan = generate_schedule(data)
        self.assertEqual(plan['busy_adjustments'], [
            {'index': 1, 'start_time': '08:15', 'end_time': '11:45'}])
        data['subjects']['Probability theory']['max_study_hours'] = 3
        plan = generate_schedule(data)
        self.assertFalse(any(a['index'] == 1 for a in plan['busy_adjustments']))
        self.assertEqual(plan['summary']['active_learning_hours_per_subject']['Probability theory'], 0)

    def test_remaining_cap_and_meal_fragments_never_create_short_generated_blocks(self):
        data = self.small_plan()
        data['study_block_size'] = 90
        data['subjects']['Probability theory']['max_study_hours'] = .5
        plan = generate_schedule(data)
        self.assertEqual(plan['summary']['active_learning_hours_per_subject']['Probability theory'], 0)
        self.assertTrue(all(b['duration_minutes'] == 90
                            for b in self.day(plan, '2026-11-02')['blocks'] if b['type'] != 'meal'))

    def test_busy_study_counts_against_the_cap(self):
        data = copy.deepcopy(self.data)
        data['subjects']['Number Theory']['max_study_hours'] = 3
        data['busy'] = [{'date': '2026-11-02', 'start_time': '08:00', 'end_time': '10:00', 'subject': 'Number Theory'}]
        plan = generate_schedule(data)
        self.assertLessEqual(plan['summary']['active_learning_hours_per_subject']['Number Theory'], 1 + 1e-8)

    def test_bad_busy_entries_are_refused(self):
        for bad in ('x', [{'date': 'soon', 'start_time': '09:00', 'end_time': '10:00'}],
                    [{'date': '2026-11-02', 'start_time': '10:00', 'end_time': '09:00'}],
                    [{'date': '2026-11-02', 'start_time': '09:00', 'end_time': '10:00', 'subject': 'Art'}]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                generate_schedule(dict(self.data, busy=bad))
