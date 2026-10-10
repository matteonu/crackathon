import type { PlannedSession, StudyData, Subject } from './study';

/** A course of one subject's semester, as GET /api/semesters/<semkez>/plan returns it. */
export interface PlanSubject {
  id: string;
  courseId: number;
  name: string;
  shortName: string;
  color: string;
  targetHours: number;
  examDate: string;
  examStart: string | null;
  examEnd: string | null;
  completed: boolean;
  nextAction: string;
  ects: number | null;
  lectureId: string;
  homepage: string | null;
  desiredGrade: number | null;
  hours: Record<string, number>;
  /** What the scheduler uses. `difficulty` is already resolved from the course rating. */
  priority: number;
  difficulty: number;
  maxStudyHours: number | null;
  lecturePerWeek: number | null;
}

/** A stretch of days the user does not study. */
export interface DayOff {
  startDate: string;
  rangeLength: number;
}

/** How the scheduler lays a day out, per semester. */
export interface Preferences {
  dayStart: string;
  dayEnd: string;
  lunch: [string, string];
  dinner: [string, string];
  studyBlockSize: number;
  studyHoursPerWeek: number | null;
  alpha: number;
  beta: number;
  daysOff: DayOff[];
  /** Weekdays studied on, 0 = Monday ... 6 = Sunday. The others count as days off. */
  studyDays: number[];
  /** Reserve the full day of every subject's exam instead of only its known time range. */
  examDaysOff: boolean;
}

/** Match the scheduler's days off: exams, unselected study weekdays and explicit date ranges. */
export function isStudyDayOff(date: string, preferences: Pick<Preferences,'studyDays'|'daysOff'> & Partial<Pick<Preferences,'examDaysOff'>>,
  subjects: readonly Pick<Subject,'examDate'>[] = []): boolean {
  const timestamp=Date.parse(date+'T12:00:00Z');
  const weekday=(new Date(timestamp).getUTCDay()+6)%7;
  return (preferences.examDaysOff!==false && subjects.some(subject=>subject.examDate===date)) || !preferences.studyDays.includes(weekday) || preferences.daysOff.some(day=>{
    const offset=(timestamp-Date.parse(day.startDate+'T12:00:00Z'))/86400000;
    return offset>=0 && offset<day.rangeLength;
  });
}

export type BlockType = 'active_learning' | 'recall' | 'meal';

/** One block of a generated plan. A meal block has no subject. */
export interface PlanBlock {
  id: number | null;
  subjectId: string | null;
  courseId: number | null;
  date: string;
  start: string;
  end: string;
  type: BlockType;
  label: string | null;
  /** 'manual' once the user drew, moved or resized it: regenerating keeps it and plans around it. */
  source: 'generated' | 'manual';
}

/** Lunch or dinner, as opposed to a break the user drew. */
export function mealBlock(block: PlanBlock): boolean {
  return block.type === 'meal' && (block.label === 'Lunch' || block.label === 'Dinner');
}

export interface PlanTotals {
  subjectId: string;
  courseId: number;
  scheduledHours: number;
  activeLearningHours: number;
}

/** What POST .../plan/generate returns and GET .../plan carries. */
export interface GeneratedPlan {
  /** null while the plan holds only slots the user drew and nothing was generated yet. */
  generatedAt: string | null;
  fromDate: string | null;
  blocks: PlanBlock[];
  summary: PlanTotals[];
}

/** The whole study plan of a semester. */
export interface Plan {
  semkez: string;
  label: string;
  start: string;
  end: string;
  subjects: PlanSubject[];
  sessions: PlannedSession[];
  preferences: Preferences;
  /** null until a schedule has been generated for this semester. */
  plan: GeneratedPlan | null;
}

/** A search result from GET /api/courses. */
export interface CourseHit {
  id: number;
  code: string;
  title: string;
  ects: number | null;
  professor: string | null;
  weeklyHours: number | null;
  levels: string[];
  language: string | null;
  added: boolean;
}

/** A semester the user can switch to, from GET /api/semesters. */
export interface SemesterOption {
  semkez: string;
  label: string;
  /** False for an old semester the VVZ sync no longer imports: its plan opens, but no courses can be added. */
  inCatalogue: boolean;
}

export interface Semesters {
  current: string;
  selected: string;
  available: SemesterOption[];
}

/** '2026W' -> 'Autumn 2026', '2027S' -> 'Spring 2027'. */
export function semesterName(semkez: string): string {
  return `${semkez.endsWith('W') ? 'Autumn' : 'Spring'} ${semkez.slice(0, 4)}`;
}

/** '2026W' -> 'HS26', '2027S' -> 'FS27'. */
export function semesterLabel(semkez: string): string {
  return `${semkez.endsWith('W') ? 'HS' : 'FS'}${semkez.slice(2, 4)}`;
}

/** The course id behind a subject id 'course-<id>', or null for anything else. */
export function courseIdOf(subjectId: string): number | null {
  const match = /^course-(\d+)$/.exec(subjectId);
  return match ? Number(match[1]) : null;
}

/** Every ISO date from start to end, inclusive. */
export function dateRange(start: string, end: string): string[] {
  const dates: string[] = [];
  for (let day = new Date(start + 'T12:00:00Z'); day.toISOString().slice(0, 10) <= end; day.setUTCDate(day.getUTCDate() + 1)) {
    dates.push(day.toISOString().slice(0, 10));
  }
  return dates;
}

/** The server's plan in the shape the app's pages use. `today` decides which week is shown first. */
export function planToData(plan: Plan, today: string): StudyData {
  const dates = dateRange(plan.start, plan.end);
  const referenceDate = today < plan.start ? plan.start : today > plan.end ? plan.end : today;
  const subjects: Subject[] = plan.subjects.map(s => {
    const subject: Subject = {
      id: s.id, courseId: s.courseId, name: s.name, shortName: s.shortName, color: s.color, targetHours: s.targetHours,
      examDate: s.examDate, completed: s.completed, nextAction: s.nextAction, lectureId: s.lectureId, hours: {...s.hours},
      examStart: s.examStart ?? null, examEnd: s.examEnd ?? null,
    };
    if (s.ects !== null) subject.ects = s.ects;
    if (s.homepage) subject.homepage = s.homepage;
    return subject;
  });
  return {version: 1, semester: plan.label, referenceDate, dates, subjects, anki: [], notes: '',
    examSession: {start: plan.start, end: plan.end}, sessions: plan.sessions.map(s => ({...s}))};
}

/** What the app shows before the plan has loaded: no subjects, a one-day range. */
export function emptyData(today: string): StudyData {
  return {version: 1, semester: '', referenceDate: today, dates: [today], subjects: [], anki: [], notes: '',
    examSession: {start: today, end: today}, sessions: []};
}

/** Minutes a block covers. Blocks never cross midnight. */
export function blockMinutes(block: PlanBlock): number {
  return minutesOf(block.end) - minutesOf(block.start);
}

export function minutesOf(time: string): number {
  return Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
}

/** Hours of study a set of blocks holds. Meals are not study. */
export function studyHours(blocks: readonly PlanBlock[]): number {
  return Math.round(blocks.filter(b => b.type !== 'meal')
    .reduce((sum, b) => sum + blockMinutes(b), 0) / 60 * 100) / 100;
}

/** A day is fulfilled only when every planned subject's recorded hours meet its own total. */
export function dayFulfilled(subjects: readonly Pick<Subject,'id'|'hours'>[], blocks: readonly PlanBlock[], date: string): boolean {
  const minutes = new Map<string,number>();
  for (const block of blocks) {
    if (block.date !== date || block.type === 'meal' || block.subjectId === null) continue;
    minutes.set(block.subjectId, (minutes.get(block.subjectId) ?? 0) + blockMinutes(block));
  }
  return minutes.size > 0 && [...minutes].every(([id, total]) => {
    const recorded = subjects.find(subject => subject.id === id)?.hours[date];
    return recorded != null && recorded >= Math.round(total / 60 * 100) / 100;
  });
}

/** The planned and recorded totals for one subject whose hours differ on a day. */
export interface HourDifference {
  subjectId: string;
  plannedHours: number;
  recordedHours: number | null;
}

/** Compare each subject once a day has a record; an unrecorded day is still awaiting study. */
export function dayHourDifferences(subjects: readonly Pick<Subject,'id'|'hours'>[], blocks: readonly PlanBlock[], date: string): HourDifference[] {
  if (!subjects.some(subject => subject.hours[date] != null)) return [];
  const minutes = new Map<string,number>();
  for (const block of blocks) {
    if (block.date !== date || block.type === 'meal' || block.subjectId === null) continue;
    minutes.set(block.subjectId, (minutes.get(block.subjectId) ?? 0) + blockMinutes(block));
  }
  return subjects.flatMap(subject => {
    const plannedHours = Math.round((minutes.get(subject.id) ?? 0) / 60 * 100) / 100;
    const recordedHours = subject.hours[date] ?? null;
    return plannedHours === Math.round((recordedHours ?? 0) * 100) / 100 ? []
      : [{subjectId:subject.id, plannedHours, recordedHours}];
  });
}

/** 'active_learning' -> 'Learning'. What the legend and the tooltips say. */
export function blockLabel(block: PlanBlock): string {
  return block.type === 'meal' ? block.label ?? 'Break'
    : block.type === 'recall' ? 'Recall' : 'Learning';
}

/** 'HH:MM' for minutes after midnight. */
export function timeOf(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}
