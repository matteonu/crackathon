import test from 'node:test';
import assert from 'node:assert/strict';
import { CALENDAR_HOURS, calendarClock, calendarEntries, calendarViewport, courseEventColumns, studyBlocksInPhase } from '../src/app/models/calendar.ts';
import type { CourseEvent } from '../src/app/models/calendar.ts';
import type { Subject } from '../src/app/models/study.ts';
import type { PlanBlock } from '../src/app/models/semester.ts';

test('preferred hours set the viewport without removing early morning or late night', () => {
  const view = calendarViewport('06:15', '19:45', 56);
  assert.equal(view.offset, 350);
  assert.equal(view.height, 756);
  assert.equal(view.fullHeight, 1344);
  assert.equal(calendarViewport('00:00', '23:59', 56).fullHeight, view.fullHeight);
  assert.deepEqual(CALENDAR_HOURS, Array.from({length: 24}, (_, hour) => hour));
  // The compact overview fits the same preferred interval at its own scale.
  const overview = calendarViewport('06:15', '19:45', 352 / 13.5);
  assert.equal(overview.height, 352);
  assert.ok(overview.offset > 0);
  assert.ok(overview.offset + overview.height < overview.fullHeight);
});

test('the live marker uses local wall time from midnight through 23:59', () => {
  assert.deepEqual(calendarClock(new Date(2026, 9, 11, 0, 0)), {minutes: 0, label: '00:00'});
  assert.deepEqual(calendarClock(new Date(2026, 9, 11, 8, 7)), {minutes: 487, label: '08:07'});
  assert.deepEqual(calendarClock(new Date(2026, 9, 11, 23, 59)), {minutes: 1439, label: '23:59'});
});

test('study blocks are shown only inside the inclusive Lernphase without modifying the saved plan', () => {
  const blocks: PlanBlock[] = ['2026-12-20','2026-12-21','2027-02-14','2027-02-15'].map((date,id)=>({id,date,start:'09:00',end:'10:00',type:'active_learning',source:'generated',courseId:1,subjectId:'course-1',label:null}));
  assert.deepEqual(studyBlocksInPhase(blocks,{start:'2026-12-21',end:'2027-02-14'}).map(block=>block.date), ['2026-12-21','2027-02-14']);
  assert.equal(blocks.length,4);
});

test('overlapping courses share columns without hiding one another; adjacent events use full width', () => {
  const event = (id:string,start:string,end:string):CourseEvent => ({id,start,end,date:'2026-10-05',subjectId:'course-1',label:'Lecture',rooms:[],inheritedFrom:null,biweekly:false});
  const entries=[event('c','10:00','12:00'),event('b','09:00','11:00'),event('a','08:00','10:00'),event('d','12:00','13:00')];
  const layout=courseEventColumns(entries);
  assert.deepEqual(layout.map(event=>[event.id,event.column,event.columns]),[['a',0,2],['b',1,2],['c',0,2],['d',0,1]]);
  assert.deepEqual(entries.map(event=>event.id),['c','b','a','d']);
});

test('today agenda includes only this date, ordered by time, with saved labels and exams', () => {
  const dayPlan = (blocks: PlanBlock[], subjects: Subject[], date: string, courses: CourseEvent[] = []) =>
    calendarEntries(blocks, courses, subjects, {start: '2026-10-11', end: '2026-10-31'}).filter(entry => entry.date === date);
  const subject: Subject = {id: 'active', name: 'Physics', shortName: 'PHY', color: '#123456', targetHours: 10,
    examDate: '2026-10-11', examStart: '11:00', examEnd: '12:00', completed: false, nextAction: '', hours: {}};
  const block = (id: number, date: string, start: string, extra: Partial<PlanBlock> = {}): PlanBlock => ({id, date, start,
    end: '15:00', subjectId: 'active', courseId: 1, type: 'active_learning', label: null, source: 'generated', ...extra});
  const blocks = [block(1, '2026-10-11', '14:00', {type: 'recall', source: 'manual'}), block(2, '2026-10-12', '09:00'),
    block(3, '2026-10-11', '09:00', {end: '10:00'}), block(4, '2026-10-11', '12:00', {end: '13:00', type: 'meal', label: 'Lunch', subjectId: null})];
  const agenda = dayPlan(blocks, [subject], '2026-10-11');
  assert.deepEqual(agenda.map(entry => [entry.start, entry.name, entry.label]), [
    ['09:00', 'Physics', 'Learning'], ['11:00', 'Physics', 'Exam'], ['12:00', 'Lunch', 'Break'], ['14:00', 'Physics', 'Recall'],
  ]);
  assert.deepEqual(blocks.map(block => block.id), [1, 2, 3, 4]);
  assert.deepEqual(dayPlan(blocks, [subject], '2026-10-10'), []);
  assert.equal(dayPlan([], [{...subject, examStart: null, examEnd: null}], '2026-10-11')[0].start, null);
  const courses = [{id: 'lecture', subjectId: 'active', date: '2026-10-10', start: '08:00', end: '10:00', label: 'Lecture', rooms: ['HG E 1'], inheritedFrom: null, biweekly: false}];
  assert.deepEqual(dayPlan([], [subject], '2026-10-10', courses).map(entry => [entry.name, entry.label, entry.type]), [['Physics', 'Lecture', 'course']]);
  assert.equal(dayPlan([], [], '2026-10-13', courses).length, 0);
});

test('overview and weekly calendar use the same events across the Lernphase boundary', () => {
  const phase = {start: '2026-12-21', end: '2027-02-14'};
  const dates = ['2026-12-20', phase.start, phase.end, '2027-02-15'];
  const blocks: PlanBlock[] = dates.map((date, id) => ({id, date, start: '09:00', end: '10:00',
    type: 'active_learning', source: 'manual', courseId: 1, subjectId: 'course-1', label: null}));
  const courses: CourseEvent[] = dates.map(date => ({id: `lecture-${date}`, date, start: '08:00', end: '09:00',
    subjectId: 'course-1', label: 'Lecture', rooms: [], inheritedFrom: null, biweekly: false}));
  const entries = calendarEntries(blocks, courses, [], phase);
  assert.deepEqual(entries.map(entry => [entry.date, entry.type]), [
    ['2026-12-20', 'course'], [phase.start, 'active_learning'], [phase.end, 'active_learning'],
  ]);
  // Weekly grid selectors keep the exact source objects, including editable slot IDs.
  assert.deepEqual(entries.flatMap(entry => entry.block ? [entry.block] : []), [blocks[1], blocks[2]]);
  assert.deepEqual(entries.flatMap(entry => entry.course ? [entry.course] : []), [courses[0]]);
  assert.equal(entries.filter(entry => entry.date === '2026-12-22').length, 0);
});

test('moved, deleted and regenerated slots change the shared agenda without changing its date to the selected week', () => {
  const phase = {start: '2026-12-21', end: '2027-02-14'};
  const today = phase.start;
  const block: PlanBlock = {id: 1, date: today, start: '09:00', end: '10:00',
    type: 'active_learning', source: 'manual', courseId: 1, subjectId: 'course-1', label: null};
  const day = (blocks: PlanBlock[]) => calendarEntries(blocks, [], [], phase).filter(entry => entry.date === today);
  assert.equal(day([block])[0].start, '09:00');
  assert.equal(day([{...block, start: '10:00', end: '11:00'}])[0].start, '10:00');
  assert.deepEqual(day([{...block, date: '2026-12-28'}]), []);
  assert.deepEqual(day([]), []);
  assert.equal(day([{...block, id: 2, source: 'generated', start: '14:00', end: '15:00'}])[0].start, '14:00');
});

