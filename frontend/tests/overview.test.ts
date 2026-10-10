import test from 'node:test';
import assert from 'node:assert/strict';
import { materialCoverage, overviewMaterials, overviewTasks } from '../src/app/models/overview.ts';
import type { Material } from '../src/app/models/material.ts';
import type { Task } from '../src/app/models/task.ts';

const file = (id: string, extra: Partial<Material> = {}): Material => ({id, subjectId: 'active', name: id, size: 0, category: 'Slides', marker: 'To read', added: 0, ...extra});
const task = (id: string, extra: Partial<Task> = {}): Task => ({id, subjectId: 'active', title: id, notes: '', due: null, priority: 'medium', done: false, completedAt: null, position: 0, createdAt: 0, ...extra});

test('overview limits documents to current courses without counting folders or decks twice', () => {
  const files = [file('nested.pdf', {parentId: 'folder'}), file('old.pdf', {subjectId: 'old-semester'}), file('folder', {kind: 'folder'}), file('deck', {kind: 'deck'}), file('notes.md', {kind: 'md'})];
  assert.deepEqual(overviewMaterials(files, new Set(['active'])).map(f => f.id), ['nested.pdf', 'notes.md']);
  assert.equal(files.length, 5);
});

test('coverage counts done documents, leaves revisits outstanding, and excludes ignored files', () => {
  const result = materialCoverage([file('read', {marker: 'Done'}), file('next'), file('again', {marker: 'Revisit'}), file('skip', {marker: 'Ignore'}), file('deck', {kind: 'deck', marker: 'Done'})]);
  assert.deepEqual(result, {counts: {'To read': 1, Revisit: 1, Done: 1, Ignore: 1}, tracked: 3, total: 4, percent: 33});
});

test('empty and all-ignored courses do not claim completion', () => {
  assert.equal(materialCoverage([]).percent, null);
  const ignored = materialCoverage([file('skip', {marker: 'Ignore'})]);
  assert.equal(ignored.percent, null);
  assert.equal(ignored.tracked, 0);
  assert.equal(ignored.total, 1);
});

test('overview tasks sort by urgency, deadline and position without exposing old or completed tasks', () => {
  const tasks = [task('low', {priority: 'low', due: '2026-01-01'}), task('medium'), task('high-undated', {priority: 'high'}), task('high-later', {priority: 'high', due: '2026-10-15'}), task('high-sooner', {priority: 'high', due: '2026-10-11'}), task('medium-first', {position: -1}), task('done', {priority: 'high', done: true}), task('old', {subjectId: 'old'})];
  const original = tasks.map(t => t.id);
  assert.deepEqual(overviewTasks(tasks, new Set(['active'])).map(t => t.id), ['high-sooner', 'high-later', 'high-undated', 'medium-first', 'medium', 'low']);
  assert.deepEqual(tasks.map(t => t.id), original);
});
