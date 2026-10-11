"""The imported course list, official timetable cache and calendar must agree."""
from unittest.mock import patch

import db
from tests.test_planner import ALICE, BOB, PlannerCase
from vvz.timetable import parse_timetable


def page(rows, code='252-0026-00L'):
    return f'''<h1>{code} Algorithms</h1><h3>Courses</h3><table><tbody><tr>
        <td>{code[:-1]}&nbsp;V</td><td>Algorithms</td><td>2 hrs</td>
        <td><table class="nested">{rows}</table></td><td>Lecturer</td></tr></tbody></table>'''


def time_row(day='Mon', time='09:15-11:00', room='1'):
    return f'''<tr><td class="td-small"><a>{day}</a></td><td class="td-small"><a>{time}</a></td>
        <td><a rel="map" href="https://ethz.ch/bin/ethz/base/rooms/map?gebaeudeMap=HG&amp;geschossMap=E&amp;raumMap={room}">HG</a></td></tr>'''


class LiveTimetableTests(PlannerCase):
    def refresh(self, semester='2026W', user=ALICE):
        response = self.client.post(f'/api/semesters/{semester}/timetable/refresh', headers=user)
        self.assertEqual(response.status_code, 200)
        return response.get_json()['events']

    def plan_events(self):
        return self.get('/api/semesters/2026W/plan').get_json()['timetable']['events']

    def expire(self):
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute('UPDATE course_timetable_cache SET retry_after=0')

    def test_parse_weekly_parallel_rooms_dated_events_and_no_times(self):
        slots = parse_timetable(page(time_row() + time_row('', room='2') + time_row('11.11.')), '252-0026-00L')
        self.assertEqual([s['weekday'] for s in slots], [0, 0, None])
        self.assertEqual([s['room'] for s in slots], ['1', '2', '1'])
        self.assertEqual(slots[2]['date'], '11.11.')
        self.assertEqual(slots[0]['start_time'], '09:15')
        self.assertEqual(parse_timetable(page(''), '252-0026-00L'), [])

    def test_unexpected_page_or_times_do_not_become_an_empty_success(self):
        for html in ('<h1>Service unavailable</h1>', page(time_row('Arranged')), page(time_row(time='unknown'))):
            with self.assertRaises(ValueError):
                parse_timetable(html, '252-0026-00L')

    def test_eth_half_semester_and_fortnightly_markers_reach_the_calendar(self):
        self.add(1)
        slots = parse_timetable(page(time_row('Mon/1') + time_row('Tue/2') + time_row('Fri/2w')), '252-0026-00L')
        with patch('vvz.timetable.fetch_timetable', return_value=slots):
            events = self.refresh()
        monday = [e for e in events if e['date'] in ('2026-09-14', '2026-11-02')]
        self.assertEqual([e['date'] for e in monday], ['2026-09-14'])
        tuesday = [e for e in events if e['date'] in ('2026-09-15', '2026-11-03')]
        self.assertEqual([e['date'] for e in tuesday], ['2026-11-03'])
        self.assertEqual(len([e for e in events if e['biweekly']]), 7)

    def test_added_course_with_empty_import_gets_current_times_then_uses_cache(self):
        self.add(1)
        self.assertEqual(self.plan_events(), [])
        slots = parse_timetable(page(time_row() + time_row('', room='2') + time_row('11.11.')), '252-0026-00L')
        with patch('vvz.timetable.fetch_timetable', return_value=slots) as fetch:
            events = self.refresh()
            self.assertEqual(len(events), 15)
            self.assertEqual(events[0]['rooms'], ['HG E 1', 'HG E 2'])
            self.assertEqual(events[0]['inheritedFrom'], None)
            self.assertEqual(self.refresh(), events)
            self.assertEqual(self.plan_events(), events)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(self.refresh(user=BOB), [])
            self.assertEqual(fetch.call_count, 1)

    def test_second_add_and_removal_update_both_refresh_and_saved_plan(self):
        def times(offering):
            return parse_timetable(page(time_row(), offering['code']), offering['code'])
        with patch('vvz.timetable.fetch_timetable', side_effect=times) as fetch:
            self.add(1)
            self.refresh()
            self.add(2)
            self.assertEqual({e['subjectId'] for e in self.refresh()}, {'course-1', 'course-2'})
            self.assertEqual(fetch.call_count, 2)
            self.client.delete('/api/semesters/2026W/courses/1', headers=ALICE)
            self.assertEqual({e['subjectId'] for e in self.refresh()}, {'course-2'})
            self.assertEqual({e['subjectId'] for e in self.plan_events()}, {'course-2'})
            self.assertEqual(fetch.call_count, 2)

    def test_failed_refresh_retains_times_and_retries_later(self):
        self.add(1)
        with patch('vvz.timetable.fetch_timetable', return_value=parse_timetable(page(time_row()), '252-0026-00L')):
            events = self.refresh()
        self.expire()
        with patch('vvz.timetable.fetch_timetable', side_effect=TimeoutError('offline')) as fetch:
            self.assertEqual(self.refresh(), events)
            self.assertEqual(self.refresh(), events)
            self.assertEqual(fetch.call_count, 1)

    def test_failure_uses_import_but_confirmed_no_times_removes_inherited_slots(self):
        self.add(1)
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute('''INSERT INTO course_timeslots (offering_id,lecture_number,weekday,start_time,end_time,inherited_from)
                    VALUES (900,'252-0026-00 V',0,'09:00','10:00','2025W')''')
        with patch('vvz.timetable.fetch_timetable', side_effect=TimeoutError('offline')):
            self.assertEqual(len(self.refresh()), 14)
        self.expire()
        with patch('vvz.timetable.fetch_timetable', return_value=[]):
            self.assertEqual(self.refresh(), [])
            self.assertEqual(self.plan_events(), [])

    def test_cache_survives_catalogue_replacement_but_different_offering_is_refetched(self):
        self.add(1)
        with patch('vvz.timetable.fetch_timetable', return_value=parse_timetable(page(time_row()), '252-0026-00L')):
            events = self.refresh()
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute('DELETE FROM course_offerings WHERE id=900')
                conn.execute("INSERT INTO course_offerings (id,course_id,semkez) VALUES (900,1,'2026W')")
        with patch('vvz.timetable.fetch_timetable') as fetch:
            self.assertEqual(self.refresh(), events)
            fetch.assert_not_called()
        with self.app.app_context():
            conn = db.get_db()
            with conn:
                conn.execute('UPDATE course_offerings SET id=905 WHERE id=900')
        with patch('vvz.timetable.fetch_timetable', return_value=[]) as fetch:
            self.assertEqual(self.refresh(), [])
            self.assertEqual(fetch.call_count, 1)

    def test_refresh_is_scoped_to_selected_user_and_semester(self):
        self.add(1)
        self.add(3, semkez='2027S')
        self.add(2, user=BOB)
        with patch('vvz.timetable.fetch_timetable', return_value=[]) as fetch:
            self.refresh()
            self.assertEqual([call.args[0]['id'] for call in fetch.call_args_list], [900])
        self.assertEqual(self.client.post('/api/semesters/2099W/timetable/refresh', headers=ALICE).status_code, 400)
