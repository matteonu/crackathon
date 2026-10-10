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

/** The position that puts a task just before or after its neighbour in the open list. A task
 *  only moves among tasks of its own priority, so it stops at the edge of its group. */
export function movedPosition(open: readonly Task[], id: string, direction: -1 | 1): number | null {
  const priority = open.find(t => t.id === id)?.priority;
  const group = open.filter(t => t.priority === priority);
  const index = group.findIndex(t => t.id === id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= group.length) return null;
  const neighbour = group[target].position;
  const beyond = group[target + direction]?.position;
  return beyond === undefined ? neighbour + direction : (neighbour + beyond) / 2;
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
