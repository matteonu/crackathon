import test from 'node:test';
import assert from 'node:assert/strict';
import { blockLabel, blockMinutes, lockedBlock, minutesOf, studyHours, timeOf } from '../src/app/models/semester.ts';
import type { PlanBlock } from '../src/app/models/semester.ts';

function block(start: string, end: string, type: PlanBlock['type'], subject: string | null = 'course-1'): PlanBlock {
  return {id: null, subjectId: subject, courseId: subject ? 1 : null, date: '2027-01-05',
    start, end, type, label: type === 'meal' ? 'Lunch' : null, source: 'generated'};
}

test('a block measures itself from its own clock times', () => {
  assert.equal(minutesOf('00:00'), 0);
  assert.equal(minutesOf('14:15'), 855);
  assert.equal(blockMinutes(block('08:00', '09:30', 'active_learning')), 90);
  assert.equal(blockMinutes(block('17:30', '18:00', 'recall')), 30);
});

test('study hours leave meals out and round to the cent', () => {
  const day = [block('08:00', '09:30', 'active_learning'), block('09:30', '11:00', 'active_learning'),
    block('12:00', '13:00', 'meal', null), block('17:30', '18:00', 'recall')];
  assert.equal(studyHours(day), 3.5);
  assert.equal(studyHours([]), 0);
  assert.equal(studyHours([block('12:00', '13:00', 'meal', null)]), 0);
  // 20 minutes is a third of an hour, and must not come back as 0.33333333333.
  assert.equal(studyHours([block('08:00', '08:20', 'active_learning')]), .33);
});

test('every block type has a word for the user', () => {
  assert.equal(blockLabel(block('08:00', '09:30', 'active_learning')), 'Learning');
  assert.equal(blockLabel(block('17:30', '18:00', 'recall')), 'Recall');
  assert.equal(blockLabel(block('12:00', '13:00', 'meal', null)), 'Lunch');
  assert.equal(blockLabel({...block('12:00', '13:00', 'meal', null), label: null}), 'Break');
});

test('hours are split by subject so the legend can add them up per course', () => {
  const blocks = [block('08:00', '09:30', 'active_learning'), block('09:30', '11:00', 'active_learning', 'course-2'),
    block('17:30', '18:00', 'recall'), block('19:00', '20:00', 'recall', 'course-2')];
  assert.equal(studyHours(blocks.filter(b => b.subjectId === 'course-1')), 2);
  assert.equal(studyHours(blocks.filter(b => b.subjectId === 'course-2')), 2.5);
  assert.equal(studyHours(blocks), 4.5);
});

test('the scheduler\'s lunch and dinner are locked, a break the user drew is not', () => {
  assert.equal(lockedBlock(block('12:00', '13:00', 'meal', null)), true);
  assert.equal(lockedBlock({...block('14:00', '15:30', 'meal', null), label: 'Break', source: 'manual'}), false);
  assert.equal(lockedBlock(block('08:00', '09:30', 'active_learning')), false);
});

test('minutes and clock times convert both ways', () => {
  for (const time of ['00:00', '08:15', '14:45', '23:59']) assert.equal(timeOf(minutesOf(time)), time);
  assert.equal(timeOf(9 * 60 + 5), '09:05');
});
