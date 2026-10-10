import test from 'node:test';
import assert from 'node:assert/strict';
import { courseIdOf, dateRange, emptyData, planToData, semesterLabel, semesterName } from '../src/app/models/semester.ts';
import type { Plan } from '../src/app/models/semester.ts';
import { validateData, validSession } from '../src/app/models/study.ts';

const plan: Plan = {
  semkez: '2026W', label: 'HS26', start: '2026-12-21', end: '2027-02-14',
  subjects: [{
    id: 'course-3204', courseId: 3204, name: 'Algorithms and Data Structures', shortName: 'Algorithms and Data Structures',
    color: '#2598A2', targetHours: 65, examDate: '2027-02-14', examStart:'09:00', examEnd:'11:00', completed: false, nextAction: '', ects: 7,
    lectureId: '252-0026-00L', homepage: 'https://www.vvz.ethz.ch/x', desiredGrade: null, hours: {'2027-01-05': 2.5},
    priority: 3, difficulty: 4, maxStudyHours: null, lecturePerWeek: 6,
  }, {
    id: 'course-7', courseId: 7, name: 'Thesis', shortName: 'Thesis', color: '#E4AC17', targetHours: 0,
    examDate: '2027-02-14', examStart:null, examEnd:null, completed: false, nextAction: '', ects: null, lectureId: '000-0000-00L', homepage: null,
    desiredGrade: null, hours: {},
    priority: 3, difficulty: 3, maxStudyHours: 20, lecturePerWeek: null,
  }],
  sessions: [{id: 's1', subjectId: 'course-3204', date: '2027-01-05', start: '09:00', hours: 2}],
  preferences: {dayStart: '08:00', dayEnd: '20:00', lunch: ['12:00', '13:00'], dinner: ['18:00', '19:00'],
    studyBlockSize: 60, studyHoursPerWeek: null, alpha: .3, beta: 5, daysOff: [], studyDays: [0, 1, 2, 3, 4, 5, 6], examDaysOff:true},
  plan: null,
};

test('semester labels and course ids', () => {
  assert.equal(semesterLabel('2026W'), 'HS26');
  assert.equal(semesterLabel('2027S'), 'FS27');
  assert.equal(courseIdOf('course-3204'), 3204);
  assert.equal(courseIdOf('number-theory'), null);
});

test('date ranges include both ends and cross months and years', () => {
  const dates = dateRange('2026-12-30', '2027-01-02');
  assert.deepEqual(dates, ['2026-12-30', '2026-12-31', '2027-01-01', '2027-01-02']);
  assert.equal(dateRange(plan.start, plan.end).length, 56);
});

test('a plan from the server becomes valid study data', () => {
  const data = planToData(plan, '2026-10-10');
  assert.equal(validateData(data), true);
  assert.equal(data.semester, 'HS26');
  assert.equal(data.referenceDate, '2026-12-21');   // today is before the phase, so its first day
  assert.deepEqual(data.examSession, {start: '2026-12-21', end: '2027-02-14'});
  assert.equal(data.subjects[0].ects, 7);
  assert.equal(data.subjects[0].examStart,'09:00');
  assert.equal(data.subjects[0].examEnd,'11:00');
  assert.equal(data.subjects[1].examStart,null);
  assert.equal('ects' in data.subjects[1], false);   // null from the server means "not set"
  assert.equal('homepage' in data.subjects[1], false);
  assert.equal(validSession(data.sessions![0], data), true);
  assert.equal(planToData(plan, '2027-03-01').referenceDate, '2027-02-14');
  assert.equal(planToData(plan, '2027-01-10').referenceDate, '2027-01-10');
});

test('no courses yet is valid, before and after loading', () => {
  assert.equal(validateData(emptyData('2026-10-10')), true);
  assert.equal(validateData(planToData({...plan, subjects: [], sessions: []}, '2026-10-10')), true);
});

test('semester names', () => {
  assert.equal(semesterName('2026W'), 'Autumn 2026');
  assert.equal(semesterName('2027S'), 'Spring 2027');
});
