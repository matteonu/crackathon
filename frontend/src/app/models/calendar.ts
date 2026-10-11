import type { PlanBlock } from './semester';
import type { Subject } from './study';

export interface CourseEvent {
  id: string; subjectId: string; date: string; start: string; end: string;
  label: string; rooms: string[]; inheritedFrom: string | null; biweekly: boolean;
}
export interface CourseTimetable { start: string; end: string; events: CourseEvent[]; }

export const CALENDAR_HOURS = Array.from({length: 24}, (_, hour) => hour);
export const DAY_MINUTES = 24 * 60;

/** Keep the full day in the document; preferences control only the initial viewport. */
export function calendarViewport(dayStart: string, dayEnd: string, hourHeight: number) {
  const minutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5));
  const start = Math.max(0, Math.min(DAY_MINUTES - 1, minutes(dayStart)));
  const end = Math.max(start + 1, Math.min(DAY_MINUTES, minutes(dayEnd)));
  return {start, end, offset: start / 60 * hourHeight, height: (end - start) / 60 * hourHeight,
    fullHeight: DAY_MINUTES / 60 * hourHeight};
}

export function calendarClock(now: Date) {
  return {minutes: now.getHours() * 60 + now.getMinutes(),
    label: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`};
}

export interface CalendarEntry {
  id: string; date: string; start: string | null; end: string | null;
  name: string; shortName: string; label: string; color: string;
  type: PlanBlock['type'] | 'exam' | 'course';
  block?: PlanBlock; course?: CourseEvent;
}

/** One event list for the weekly calendar and today's agenda. Filter by date only after
 * combining course times before the Lernphase, saved study slots during it, and exams. */
export function calendarEntries(blocks: readonly PlanBlock[], courses: readonly CourseEvent[],
  subjects: readonly Subject[], phase: {start: string; end: string}): CalendarEntry[] {
  const byId = new Map(subjects.map(subject => [subject.id, subject]));
  const entries: CalendarEntry[] = studyBlocksInPhase(blocks, phase).map((block, index) => {
    const subject = block.subjectId ? byId.get(block.subjectId) : undefined;
    const name = subject?.name ?? block.label ?? (block.type === 'meal' ? 'Break' : 'Study session');
    return {id: `block-${block.id ?? `${block.date}-${index}`}`, date: block.date,
      start: block.start, end: block.end, name, shortName: subject?.shortName ?? name,
      label: block.type === 'meal' ? 'Break' : block.type === 'recall' ? 'Recall' : 'Learning',
      color: subject?.color ?? 'var(--muted)', type: block.type, block};
  });
  for (const course of courses.filter(course => course.date < phase.start)) {
    const subject = byId.get(course.subjectId);
    entries.push({id: course.id, date: course.date, start: course.start, end: course.end,
      name: subject?.name ?? 'Course', shortName: subject?.shortName ?? 'Course',
      label: course.label, color: subject?.color ?? 'var(--muted)', type: 'course', course});
  }
  for (const subject of subjects.filter(subject => subject.examDate)) {
    entries.push({id: `exam-${subject.id}`, date: subject.examDate,
      start: subject.examStart ?? null, end: subject.examEnd ?? null,
      name: subject.name, shortName: subject.shortName, label: 'Exam', color: subject.color, type: 'exam'});
  }
  return entries.sort((a, b) => a.date.localeCompare(b.date) || (a.start ?? '').localeCompare(b.start ?? '')
    || (a.end ?? '').localeCompare(b.end ?? '') || a.id.localeCompare(b.id));
}

/** Course events never replace or alter saved study blocks inside the Lernphase. */
export function studyBlocksInPhase(blocks: readonly PlanBlock[], phase: {start: string; end: string}): PlanBlock[] {
  return blocks.filter(block => block.date >= phase.start && block.date <= phase.end);
}

/** Lay simultaneous classes beside each other, including chained overlaps. */
export function courseEventColumns<T extends {id: string; start: string; end: string}>(events: readonly T[]) {
  const sorted = [...events].sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end) || a.id.localeCompare(b.id));
  const result: (T & {column: number; columns: number})[] = [];
  let group: typeof result = [], ends: string[] = [], groupEnd = '';
  const finish = () => { for (const entry of group) entry.columns = ends.length; result.push(...group); };
  for (const event of sorted) {
    if (group.length && event.start >= groupEnd) { finish(); group = []; ends = []; groupEnd = ''; }
    let column = ends.findIndex(end => end <= event.start);
    if (column < 0) column = ends.length;
    ends[column] = event.end;
    groupEnd = event.end > groupEnd ? event.end : groupEnd;
    group.push({...event, column, columns: 1});
  }
  finish();
  return result;
}
