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
        # What is left of a cut block is still used when it is long enough.
        self.assertIn('11:15', [b['start_time'] for b in self.day(plan, '2026-11-02')['blocks']])

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
