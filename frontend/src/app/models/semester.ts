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
}

export interface PlanTotals {
  subjectId: string;
  courseId: number;
  scheduledHours: number;
  activeLearningHours: number;
}

/** What POST .../plan/generate returns and GET .../plan carries. */
export interface GeneratedPlan {
  generatedAt: string;
  fromDate: string;
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

/** 'active_learning' -> 'Learning'. What the legend and the tooltips say. */
export function blockLabel(block: PlanBlock): string {
  return block.type === 'meal' ? block.label ?? 'Break'
    : block.type === 'recall' ? 'Recall' : 'Learning';
}
