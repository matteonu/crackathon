import type { Material, MaterialMarker } from './material';
import type { Task } from './task';
import type { PlanBlock } from './semester';
import type { Subject } from './study';

export const OVERVIEW_GREETINGS = [
  'Welcome Back USERNAME.',
  'Time to lock in USERNAME.',
  "Let's get started USERNAME.",
] as const;

export const MATERIAL_STATES: readonly {marker: MaterialMarker; key: string; icon: string}[] = [
  {marker: 'To read', key: 'unread', icon: 'book'},
  {marker: 'Revisit', key: 'revisit', icon: 'clock'},
  {marker: 'Done', key: 'done', icon: 'check'},
  {marker: 'Ignore', key: 'ignored', icon: 'minus'},
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
  const total = tracked + counts.Ignore;
  // Ignored files stay on the material board but do not count towards coverage.
  const segments = ['Done', 'Revisit', 'To read'].map(marker => {
    const state = MATERIAL_STATES.find(state => state.marker === marker)!;
    const count = counts[state.marker];
    const percent = tracked ? count / tracked * 100 : 0;
    return {...state, count, percent, label: `${marker}: ${count} of ${tracked} files (${Math.round(percent * 10) / 10}%)`};
  });
  return {counts, tracked, total, percent: tracked ? Math.round(counts.Done / tracked * 100) : null,
    segments, description: tracked ? segments.map(segment => segment.label).join('; ') : 'No material to cover'};
}

export function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** Use the saved plan, independent of the week selected on the Schedule page. */
export function overviewDayPlan(blocks: readonly PlanBlock[], subjects: readonly Subject[], date: string) {
  const byId = new Map(subjects.map(subject => [subject.id, subject]));
  const entries = blocks.filter(block => block.date === date).map((block, index) => {
    const subject = block.subjectId ? byId.get(block.subjectId) : undefined;
    return {
      id: `block-${block.id ?? index}`,
      start: block.start as string | null, end: block.end as string | null,
      name: subject?.name ?? block.label ?? (block.type === 'meal' ? 'Break' : 'Study session'),
      label: block.type === 'meal' ? 'Break' : block.type === 'recall' ? 'Recall' : 'Learning',
      color: subject?.color ?? 'var(--muted)', type: block.type as PlanBlock['type'] | 'exam',
    };
  });
  for (const subject of subjects.filter(subject => subject.examDate === date)) {
    entries.push({id: `exam-${subject.id}`, start: subject.examStart ?? null, end: subject.examEnd ?? null,
      name: subject.name, label: 'Exam', color: subject.color, type: 'exam'});
  }
  return entries.sort((a, b) => (a.start ?? '').localeCompare(b.start ?? '')
    || (a.end ?? '').localeCompare(b.end ?? '') || a.id.localeCompare(b.id));
}

/** Urgency wins; within it, earlier deadlines come before undated tasks. */
export function overviewTasks(tasks: readonly Task[], subjectIds: ReadonlySet<string>): Task[] {
  const rank = {high: 0, medium: 1, low: 2};
  return tasks.filter(task => subjectIds.has(task.subjectId) && !task.done)
    .sort((a, b) => rank[a.priority] - rank[b.priority]
      || (a.due ?? '9999-12-31').localeCompare(b.due ?? '9999-12-31')
      || a.position - b.position || b.createdAt - a.createdAt || a.id.localeCompare(b.id));
}
