import test from 'node:test';
import assert from 'node:assert/strict';
import { localDateKey, materialCoverage, overviewDayPlan, overviewMaterials, overviewTasks } from '../src/app/models/overview.ts';
import type { Material } from '../src/app/models/material.ts';
import type { Task } from '../src/app/models/task.ts';
import type { PlanBlock } from '../src/app/models/semester.ts';
import type { Subject } from '../src/app/models/study.ts';

const file = (id: string, extra: Partial<Material> = {}): Material => ({id, subjectId: 'active', name: id, size: 0, category: 'Slides', marker: 'To read', added: 0, ...extra});
const task = (id: string, extra: Partial<Task> = {}): Task => ({id, subjectId: 'active', title: id, notes: '', due: null, priority: 'medium', done: false, completedAt: null, position: 0, createdAt: 0, ...extra});

test('overview limits documents to current courses without counting folders or decks twice', () => {
  const files = [file('nested.pdf', {parentId: 'folder'}), file('old.pdf', {subjectId: 'old-semester'}), file('folder', {kind: 'folder'}), file('deck', {kind: 'deck'}), file('notes.md', {kind: 'md'}), file('ignored.pdf', {marker: 'Ignore'})];
  assert.deepEqual(overviewMaterials(files, new Set(['active'])).map(f => f.id), ['ignored.pdf', 'nested.pdf', 'notes.md']);
  assert.equal(files.length, 6);
});

test('coverage excludes ignored files from its denominator and segments', () => {
  const result = materialCoverage([file('read', {marker: 'Done'}), file('next'), file('again', {marker: 'Revisit'}), file('skip', {marker: 'Ignore'}), file('deck', {kind: 'deck', marker: 'Done'})]);
  assert.deepEqual(result.counts, {'To read': 1, Revisit: 1, Done: 1, Ignore: 1});
  assert.equal(result.total, 4);
  assert.equal(result.tracked, 3);
  assert.equal(result.percent, 33);
  assert.deepEqual(result.segments.map(segment => segment.marker), ['Done', 'Revisit', 'To read']);
  assert.ok(result.segments.every(segment => Math.abs(segment.percent - 100 / 3) < 1e-10));
  assert.match(result.description, /Done: 1 of 3 files \(33.3%\)/);
  assert.doesNotMatch(result.description, /Ignore/);
  assert.equal(materialCoverage([file('done', {marker: 'Done'}), file('skip', {marker: 'Ignore'})]).percent, 100);
});

test('empty and all-ignored courses do not claim completion', () => {
  assert.equal(materialCoverage([]).percent, null);
  const ignored = materialCoverage([file('skip', {marker: 'Ignore'})]);
  assert.equal(ignored.percent, null);
  assert.equal(ignored.tracked, 0);
  assert.equal(ignored.total, 1);
  assert.ok(ignored.segments.every(segment => segment.percent === 0));
  assert.equal(ignored.description, 'No material to cover');
  assert.ok(materialCoverage([]).segments.every(segment => segment.percent === 0));
});

test('uneven material splits fill the bar without rounding gaps', () => {
  const result = materialCoverage([file('a'), file('b', {marker: 'Done'}), file('c', {marker: 'Revisit'})]);
  assert.ok(Math.abs(result.segments.reduce((sum, segment) => sum + segment.percent, 0) - 100) < 1e-10);
});

test('today agenda includes only this date, ordered by time, with saved labels and exams', () => {
  const subject: Subject = {id: 'active', name: 'Physics', shortName: 'PHY', color: '#123456', targetHours: 10,
    examDate: '2026-10-11', examStart: '11:00', examEnd: '12:00', completed: false, nextAction: '', hours: {}};
  const block = (id: number, date: string, start: string, extra: Partial<PlanBlock> = {}): PlanBlock => ({id, date, start,
    end: '15:00', subjectId: 'active', courseId: 1, type: 'active_learning', label: null, source: 'generated', ...extra});
  const blocks = [block(1, '2026-10-11', '14:00', {type: 'recall', source: 'manual'}), block(2, '2026-10-12', '09:00'),
    block(3, '2026-10-11', '09:00', {end: '10:00'}), block(4, '2026-10-11', '12:00', {end: '13:00', type: 'meal', label: 'Lunch', subjectId: null})];
  const agenda = overviewDayPlan(blocks, [subject], '2026-10-11');
  assert.deepEqual(agenda.map(entry => [entry.start, entry.name, entry.label]), [
    ['09:00', 'Physics', 'Learning'], ['11:00', 'Physics', 'Exam'], ['12:00', 'Lunch', 'Break'], ['14:00', 'Physics', 'Recall'],
  ]);
  assert.deepEqual(blocks.map(block => block.id), [1, 2, 3, 4]);
  assert.deepEqual(overviewDayPlan(blocks, [subject], '2026-10-10'), []);
  assert.equal(overviewDayPlan([], [{...subject, examStart: null, examEnd: null}], '2026-10-11')[0].start, null);
});

test('today uses the local calendar date, including near midnight', () => {
  assert.equal(localDateKey(new Date(2026, 9, 11, 0, 5)), '2026-10-11');
  assert.equal(localDateKey(new Date(2026, 9, 11, 23, 55)), '2026-10-11');
});

test('overview tasks sort by urgency, deadline and position without exposing old or completed tasks', () => {
  const tasks = [task('low', {priority: 'low', due: '2026-01-01'}), task('medium'), task('high-undated', {priority: 'high'}), task('high-later', {priority: 'high', due: '2026-10-15'}), task('high-sooner', {priority: 'high', due: '2026-10-11'}), task('medium-first', {position: -1}), task('done', {priority: 'high', done: true}), task('old', {subjectId: 'old'})];
  const original = tasks.map(t => t.id);
  assert.deepEqual(overviewTasks(tasks, new Set(['active'])).map(t => t.id), ['high-sooner', 'high-later', 'high-undated', 'medium-first', 'medium', 'low']);
  assert.deepEqual(tasks.map(t => t.id), original);
});
