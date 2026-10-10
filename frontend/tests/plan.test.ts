import test from 'node:test';
import assert from 'node:assert/strict';
import { blockLabel, blockMinutes, dayFulfilled, dayHourDifferences, isStudyDayOff, mealBlock, minutesOf, studyHours, timeOf } from '../src/app/models/semester.ts';
import type { PlanBlock } from '../src/app/models/semester.ts';
import { validExamTimes } from '../src/app/models/study.ts';

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

test('lunch and dinner are meals, a break the user drew is not', () => {
  assert.equal(mealBlock(block('12:00', '13:00', 'meal', null)), true);
  assert.equal(mealBlock({...block('18:00', '19:00', 'meal', null), label: 'Dinner', source: 'manual'}), true);
  assert.equal(mealBlock({...block('14:00', '15:30', 'meal', null), label: 'Break', source: 'manual'}), false);
  assert.equal(mealBlock(block('08:00', '09:30', 'active_learning')), false);
});

test('minutes and clock times convert both ways', () => {
  for (const time of ['00:00', '08:15', '14:45', '23:59']) assert.equal(timeOf(minutesOf(time)), time);
  assert.equal(timeOf(9 * 60 + 5), '09:05');
});

test('days off follow selected study weekdays, including studying on weekends', () => {
  const preferences={studyDays:[0,2,5,6],daysOff:[]};
  assert.equal(isStudyDayOff('2027-01-04',preferences),false); // Monday
  assert.equal(isStudyDayOff('2027-01-05',preferences),true);  // Tuesday
  assert.equal(isStudyDayOff('2027-01-06',preferences),false); // Wednesday
  assert.equal(isStudyDayOff('2027-01-08',preferences),true);  // Friday
  assert.equal(isStudyDayOff('2027-01-09',preferences),false); // Saturday
  assert.equal(isStudyDayOff('2027-01-10',preferences),false); // Sunday
});

test('explicit days off cover their full date ranges across years and daylight saving', () => {
  const preferences={studyDays:[0,1,2,3,4,5,6],daysOff:[
    {startDate:'2026-12-31',rangeLength:3},{startDate:'2027-03-27',rangeLength:3}]};
  assert.equal(isStudyDayOff('2026-12-30',preferences),false);
  for(const date of ['2026-12-31','2027-01-01','2027-01-02','2027-03-27','2027-03-28','2027-03-29']) {
    assert.equal(isStudyDayOff(date,preferences),true,date);
  }
  assert.equal(isStudyDayOff('2027-01-03',preferences),false);
  assert.equal(isStudyDayOff('2027-03-30',preferences),false);
});

test('any subjects exam date is a day off even on a chosen study weekday', () => {
  const preferences={studyDays:[0,1,2,3,4,5,6],daysOff:[]};
  const subjects=[{examDate:'2027-01-05'},{examDate:'2027-01-07'}];
  assert.equal(isStudyDayOff('2027-01-05',preferences,subjects),true);
  assert.equal(isStudyDayOff('2027-01-07',preferences,subjects),true);
  assert.equal(isStudyDayOff('2027-01-06',preferences,subjects),false);
});

test('disabling exam days off keeps explicit days off and selected weekdays in force', () => {
  const preferences={studyDays:[0,1,2,3,4],daysOff:[{startDate:'2027-01-07',rangeLength:1}],examDaysOff:false};
  const subjects=[{examDate:'2027-01-05'},{examDate:'2027-01-07'},{examDate:'2027-01-09'}];
  assert.equal(isStudyDayOff('2027-01-05',preferences,subjects),false);
  assert.equal(isStudyDayOff('2027-01-07',preferences,subjects),true);
  assert.equal(isStudyDayOff('2027-01-09',preferences,subjects),true);
  assert.equal(isStudyDayOff('2027-01-05',{...preferences,examDaysOff:true},subjects),true);
});

test('exam times are either unknown or a complete valid range on the same date', () => {
  for(const [start,end] of [[null,null],[undefined,undefined],['09:00','11:00'],['00:00','23:59']]) {
    assert.equal(validExamTimes(start,end),true);
  }
  for(const [start,end] of [['09:00',null],[null,'11:00'],['09:00','09:00'],['11:00','09:00'],
    ['23:00','01:00'],['9:00','11:00'],['09:00','24:00'],['09:60','11:00'],['',''],[9,11]]) {
    assert.equal(validExamTimes(start,end),false,`${start} to ${end}`);
  }
});

test('a day is fulfilled per subject, including custom study and recall but excluding meals', () => {
  const date='2027-01-05';
  const blocks=[block('08:00','09:30','active_learning'),
    {...block('10:00','11:00','active_learning'),source:'manual' as const},
    block('17:00','17:30','recall'),block('13:00','15:00','active_learning','course-2'),
    block('12:00','13:00','meal',null),{...block('08:00','12:00','active_learning'),date:'2027-01-06'}];
  const subjects=[{id:'course-1',hours:{[date]:3}},{id:'course-2',hours:{[date]:2}},
    {id:'course-3',hours:{[date]:1}}];
  assert.equal(dayFulfilled(subjects,blocks,date),true);
  // The right combined total in the wrong subjects does not fulfill the plan.
  assert.equal(dayFulfilled([{id:'course-1',hours:{[date]:4}},{id:'course-2',hours:{[date]:1}}],blocks,date),false);
  assert.equal(dayFulfilled([{id:'course-1',hours:{[date]:3}},{id:'course-2',hours:{}}],blocks,date),false);
  assert.equal(dayFulfilled(subjects,blocks,'2027-01-06'),false);
  assert.equal(dayFulfilled([{id:'course-1',hours:{[date]:4}},{id:'course-2',hours:{[date]:3}}],blocks,date),true);
});

test('an empty or meal-only day cannot be marked fulfilled, and fractional study hours are rounded', () => {
  const date='2027-01-05';
  const subjects=[{id:'course-1',hours:{[date]:.33}}];
  assert.equal(dayFulfilled(subjects,[],date),false);
  assert.equal(dayFulfilled(subjects,[block('12:00','13:00','meal',null)],date),false);
  assert.equal(dayFulfilled(subjects,[block('08:00','08:20','active_learning')],date),true);
  assert.equal(dayFulfilled([{id:'course-1',hours:{[date]:0}}],[block('08:00','08:20','active_learning')],date),false);
});

test('unrecorded days have no mismatch, but an explicit zero-hour record counts', () => {
  const date='2027-01-05', blocks=[block('08:00','09:00','active_learning')];
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{}}],blocks,date),[]);
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{[date]:null}}],blocks,date),[]);
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{'2027-01-04':2}}],blocks,date),[]);
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{[date]:0}}],blocks,date),[
    {subjectId:'course-1',plannedHours:1,recordedHours:0}]);
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{[date]:0}}],[],date),[]);
});

test('mismatches compare subjects even when daily totals match and include unplanned study', () => {
  const date='2027-01-05';
  const blocks=[block('08:00','09:00','active_learning'),
    {...block('09:00','09:30','recall'),source:'manual' as const},
    block('10:00','11:00','active_learning','course-2'),block('12:00','13:00','meal',null),
    {...block('08:00','12:00','active_learning'),date:'2027-01-06'}];
  assert.deepEqual(dayHourDifferences([
    {id:'course-1',hours:{[date]:1.5}},{id:'course-2',hours:{[date]:1}}],blocks,date),[]);
  assert.deepEqual(dayHourDifferences([
    {id:'course-1',hours:{[date]:1}},{id:'course-2',hours:{[date]:1.5}}],blocks,date),[
    {subjectId:'course-1',plannedHours:1.5,recordedHours:1},
    {subjectId:'course-2',plannedHours:1,recordedHours:1.5}]);
  assert.deepEqual(dayHourDifferences([
    {id:'course-1',hours:{[date]:1.5}},{id:'course-2',hours:{}},{id:'course-3',hours:{[date]:2}}],blocks,date),[
    {subjectId:'course-2',plannedHours:1,recordedHours:null},
    {subjectId:'course-3',plannedHours:0,recordedHours:2}]);
});

test('mismatch comparisons sum a subjects blocks before rounding to recorded precision', () => {
  const date='2027-01-05';
  const blocks=[block('08:00','08:20','active_learning'),block('08:20','08:40','recall')];
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{[date]:.67}}],blocks,date),[]);
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{[date]:.66}}],blocks,date),[
    {subjectId:'course-1',plannedHours:.67,recordedHours:.66}]);
  assert.deepEqual(dayHourDifferences([{id:'course-1',hours:{[date]:1}}],[],date),[
    {subjectId:'course-1',plannedHours:0,recordedHours:1}]);
});
