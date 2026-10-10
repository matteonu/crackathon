// No value imports from other models: the node test runner wants './x.ts' paths and the Angular
// compiler refuses them, so the few date helpers needed here live here (same rules as study.ts).
function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}

function nextDay(iso: string): string {
  const date = new Date(iso + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

function formatDay(iso: string, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat('en-GB', {...options, timeZone: 'UTC'}).format(new Date(iso + 'T12:00:00Z'));
}

export type Priority = 'high' | 'medium' | 'low';

/** Highest first: open tasks sort in this order, then by their manual position. */
export const PRIORITIES: readonly {value: Priority; label: string}[] = [
  {value: 'high', label: 'High'}, {value: 'medium', label: 'Medium'}, {value: 'low', label: 'Low'},
];

export function priorityRank(priority: Priority): number {
  return PRIORITIES.findIndex(p => p.value === priority);
}

/** One to-do in a subject's list. Stored on the server; see services/task-store.ts. */
export interface Task {
  id: string;
  subjectId: string;
  title: string;
  notes: string;
  due: string | null;        // 'YYYY-MM-DD'
  priority: Priority;
  done: boolean;
  completedAt: number | null;
  position: number;          // manual order among open tasks of the same priority, ascending
  createdAt: number;
}

export const MAX_TASK_TITLE = 500;
export const MAX_TASK_NOTES = 5000;

/** Collapse whitespace; empty means "not a title". */
export function cleanTitle(value: string): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, MAX_TASK_TITLE);
}

export function openTasks(tasks: readonly Task[], subjectId: string): Task[] {
  return tasks.filter(t => t.subjectId === subjectId && !t.done)
    .sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority) || a.position - b.position || b.createdAt - a.createdAt);
}

export function doneTasks(tasks: readonly Task[], subjectId: string): Task[] {
  return tasks.filter(t => t.subjectId === subjectId && t.done)
    .sort((a, b) => (b.completedAt ?? 0) - (a.completedAt ?? 0));
}

/** The position a new task gets so it lands at the top of its subject's list. */
export function topPosition(tasks: readonly Task[], subjectId: string): number {
  const positions = tasks.filter(t => t.subjectId === subjectId).map(t => t.position);
  return (positions.length ? Math.min(...positions) : 0) - 1;
}

/** Where a dragged open task lands when dropped at `index` of the open list (the index it has
 *  after the drop). It keeps its priority if that still sorts between its new neighbours, and
 *  otherwise takes the priority of the task above it (or below, at the very top), so dragging
 *  into another group re-prioritises it. Null when nothing changes. */
export function droppedPlacement(open: readonly Task[], id: string, index: number): {priority: Priority; position: number} | null {
  const from = open.findIndex(t => t.id === id);
  if (from < 0) return null;
  const task = open[from];
  const rest = open.filter(t => t.id !== id);
  const to = Math.max(0, Math.min(index, rest.length));
  if (to === from) return null;
  const before = rest[to - 1], after = rest[to];
  const rank = priorityRank(task.priority);
  const fits = (!before || priorityRank(before.priority) <= rank) && (!after || rank <= priorityRank(after.priority));
  const priority = fits ? task.priority : (before ?? after)!.priority;
  const low = before?.priority === priority ? before.position : undefined;
  const high = after?.priority === priority ? after.position : undefined;
  const position = low !== undefined && high !== undefined ? (low + high) / 2
    : low !== undefined ? low + 1 : high !== undefined ? high - 1 : task.position;
  return {priority, position};
}

export type DueState = 'overdue' | 'today' | 'tomorrow' | 'upcoming';

export function dueState(due: string, today: string): DueState {
  if (due < today) return 'overdue';
  if (due === today) return 'today';
  if (due === nextDay(today)) return 'tomorrow';
  return 'upcoming';
}

export function dueLabel(due: string, today: string): string {
  const state = dueState(due, today);
  if (state === 'today') return 'Today';
  if (state === 'tomorrow') return 'Tomorrow';
  const sameYear = due.slice(0, 4) === today.slice(0, 4);
  return formatDay(due, sameYear ? {day: 'numeric', month: 'short'} : {day: 'numeric', month: 'short', year: 'numeric'});
}

export function validTask(value: unknown): value is Task {
  if (!value || typeof value !== 'object') return false;
  const t = value as Task;
  return typeof t.id === 'string' && !!t.id && typeof t.subjectId === 'string' && !!t.subjectId
    && typeof t.title === 'string' && !!t.title && t.title.length <= MAX_TASK_TITLE
    && typeof t.notes === 'string' && t.notes.length <= MAX_TASK_NOTES
    && (t.due === null || isIsoDate(t.due)) && PRIORITIES.some(p => p.value === t.priority) && typeof t.done === 'boolean'
    && (t.completedAt === null || Number.isFinite(t.completedAt))
    && Number.isFinite(t.position) && Number.isFinite(t.createdAt);
}
