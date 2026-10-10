import type { Material, MaterialMarker } from './material';
import type { Task } from './task';

export const OVERVIEW_QUOTES = [
  'Azerbaijan is not Dagestan',
  'Go back to Dagestan and Forget',
  "If you don't like, go back to Dagestan",
] as const;

export const MATERIAL_STATES: readonly {marker: MaterialMarker; key: string; icon: string; hint: string}[] = [
  {marker: 'To read', key: 'unread', icon: 'book', hint: 'Up next'},
  {marker: 'Revisit', key: 'revisit', icon: 'clock', hint: 'Needs another look'},
  {marker: 'Done', key: 'done', icon: 'check', hint: 'Covered'},
  {marker: 'Ignore', key: 'ignored', icon: 'minus', hint: 'Outside your study scope'},
];

const isDocument = (file: Material): boolean => file.kind !== 'folder' && file.kind !== 'deck';

/** Only the selected semester's documents; folders and generated decks are not extra reading. */
export function overviewMaterials(files: readonly Material[], subjectIds: ReadonlySet<string>): Material[] {
  return files.filter(file => subjectIds.has(file.subjectId) && isDocument(file))
    .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

export function materialCoverage(files: readonly Material[]) {
  const counts: Record<MaterialMarker, number> = {'To read': 0, Revisit: 0, Done: 0, Ignore: 0};
  for (const file of files) if (isDocument(file)) counts[file.marker]++;
  const tracked = counts['To read'] + counts.Revisit + counts.Done;
  return {counts, tracked, total: tracked + counts.Ignore, percent: tracked ? Math.round(counts.Done / tracked * 100) : null};
}

/** Urgency wins; within it, earlier deadlines come before undated tasks. */
export function overviewTasks(tasks: readonly Task[], subjectIds: ReadonlySet<string>): Task[] {
  const rank = {high: 0, medium: 1, low: 2};
  return tasks.filter(task => subjectIds.has(task.subjectId) && !task.done)
    .sort((a, b) => rank[a.priority] - rank[b.priority]
      || (a.due ?? '9999-12-31').localeCompare(b.due ?? '9999-12-31')
      || a.position - b.position || b.createdAt - a.createdAt || a.id.localeCompare(b.id));
}
