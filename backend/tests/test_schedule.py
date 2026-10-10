import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from schedule_planner.dayrange import DayRange
from schedule_planner.main import generate_schedule
from schedule_planner.schedule import Schedule


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(Path(__file__).with_name('example_input.json').read_text())

    def test_json_and_independent_requests(self):
        original = copy.deepcopy(self.data)
        first = generate_schedule(self.data)
        self.assertEqual(first, generate_schedule(self.data))
        self.assertEqual(self.data, original)
        self.assertEqual(json.loads(json.dumps(first, allow_nan=False)), first)
        self.assertEqual(len(first['weeks']), 3)

    def test_blocks_history_caps_and_capacity(self):
        result = generate_schedule(self.data)
        totals = {name: 0 for name in self.data['subjects']}
        active = dict(totals)
        for week in result['weeks']:
            for day in week['days']:
                recall = set()
                subjects = set()
                recall_started = False
                end = '00:00'
                if day['is_day_off']:
                    self.assertEqual(day['blocks'], [])
                for block in day['blocks']:
                    self.assertGreaterEqual(block['start_time'], end)
                    self.assertGreater(block['end_time'], block['start_time'])
                    end = block['end_time']
                    if block['type'] == 'meal':
                        continue
                    name = block['subject']
                    self.assertLess(day['date'], self.data['subjects'][name]['examdate'])
                    self.assertLessEqual(block['duration_minutes'], self.data['study_block_size'])
                    subjects.add(name)
                    totals[name] += block['duration_minutes'] / 60
                    if block['type'] == 'recall':
                        self.assertNotIn(name, recall)
                        recall.add(name)
                        recall_started = True
                    else:
                        self.assertFalse(recall_started)
                        active[name] += block['duration_minutes'] / 60
                self.assertEqual(subjects, recall)
            for name in totals:
                self.assertAlmostEqual(totals[name], week['cumulative_hours_per_subject'][name])
            self.assertLessEqual(sum(week['scheduled_hours_per_subject'].values()), week['available_hours'] + 1e-8)
        self.assertLessEqual(active['Number Theory'], 12)
        self.assertGreater(totals['Number Theory'], active['Number Theory'])
        self.assertEqual(totals, result['summary']['scheduled_hours_per_subject'])
        self.assertEqual(active, result['summary']['active_learning_hours_per_subject'])

    def test_empty_week_partial_week_and_zero_cap(self):
        self.data['exam_session']['range_length'] = 9
        self.data['days_off'] = [{'start_date': '2026-11-01', 'range_length': 7}]
        for subject in self.data['subjects'].values():
            subject['max_study_hours'] = 0
        result = generate_schedule(self.data)
        self.assertEqual(result['weeks'][0]['available_hours'], 0)
        self.assertEqual(result['weeks'][1]['range_length'], 2)
        self.assertEqual(result['weeks'][1]['available_hours'], 20)
        self.assertTrue(all(value == 0 for value in result['summary']['active_learning_hours_per_subject'].values()))

    def test_regeneration_and_week_history(self):
        data = copy.deepcopy(self.data)
        data['exam_session'] = DayRange.from_value(data['exam_session'])
        data['days_off'] = [DayRange.from_value(day) for day in data['days_off']]
        for subject in data['subjects'].values():
            subject['examdate'] = DayRange.from_value(subject['examdate'])
        planner = Schedule(data, '08:00', '20:00', ('12:00', '13:00'), ('18:00', '19:00'))
        planner.generate_schedule()
        first = planner.to_dict()
        planner.generate_schedule()
        self.assertEqual(first, planner.to_dict())
        totals = planner.hours_studied_per_subject
        planner.next_week()
        self.assertEqual(totals, planner.hours_studied_per_subject)

    def test_invalid_input(self):
        for field, value in [('study_block_size', 0), ('day_start', 'bad'),
                             ('day_end', '07:00'), ('alpha', float('nan')),
                             ('beta', 0), ('days_off', 'bad'), ('subjects', {})]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                generate_schedule(dict(self.data, **{field: value}))
        for field, value in [('priority', 0), ('max_study_hours', -1), ('examdate', 'bad')]:
            data = copy.deepcopy(self.data)
            data['subjects']['Geometry'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                generate_schedule(data)

    def test_date_range_and_cli(self):
        r = DayRange.from_value({'start_date': '2026-12-30', 'range_length': 4})
        self.assertEqual(r.end_date.isoformat(), '2027-01-02')
        self.assertEqual(r[-1], r.end_date)
        result = subprocess.run([sys.executable, '-m', 'schedule_planner.main'],
                                input=json.dumps(self.data), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('weeks', json.loads(result.stdout))
        bad = subprocess.run([sys.executable, '-m', 'schedule_planner.main'],
                             input='{}', capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn('error', json.loads(bad.stderr))


if __name__ == '__main__':
    unittest.main()
