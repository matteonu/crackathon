export interface Subject {
  id: string;
  name: string;
  shortName: string;
  color: string;
  targetHours: number;
  examDate: string;
  examStart?: string | null;
  examEnd?: string | null;
  completed: boolean;
  nextAction: string;
  hours: Record<string, number | null>;
  ects?: number;
  lectureId?: string;
  homepage?: string;
  /** The VVZ course this subject is (id 'course-<courseId>'). */
  courseId?: number;
}

export interface AnkiDeck {
  subjectId?: string;
  name: string;
  total: number;
  mature: number;
  learned: number;
  left: number;
}

export interface StudyData {
  version: number;
  semester: string;
  referenceDate: string;
  dates: string[];
  subjects: Subject[];
  anki: AnkiDeck[];
  notes: string;
  examSession?: { start: string; end: string };
  sessions?: PlannedSession[];
}

export interface PlannedSession {
  id: string;
  subjectId: string;
  date: string;
  start: string;
  hours: number;
}

export function segmentedDate(day: string, month: string, year: string): string | null {
  if (!/^\d{1,2}$/.test(day) || !/^\d{1,2}$/.test(month) || !/^\d{4}$/.test(year)) return null;
  const iso = `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
  return isValidDate(iso) ? iso : null;
}

export function safeHomepage(value: string): boolean {
  try { return ['https:', 'http:'].includes(new URL(value).protocol); } catch { return false; }
}

export function validSession(session: PlannedSession, data: StudyData): boolean {
  const bounds = data.examSession ?? {start: data.dates[0], end: data.dates.at(-1)!};
  return !!session && typeof session.id === 'string' && !!session.id
    && data.subjects.some(s => s?.id === session.subjectId) && data.dates.includes(session.date)
    && session.date >= bounds.start && session.date <= bounds.end
    && /^([01]\d|2[0-3]):[0-5]\d$/.test(session.start)
    && Number.isFinite(session.hours) && session.hours > 0 && session.hours <= 24
    && Number(session.start.slice(0,2)) + Number(session.start.slice(3))/60 + session.hours <= 24;
}

export function sessionsOverlap(a: PlannedSession, b: PlannedSession): boolean {
  const minutes = (s: PlannedSession) => Number(s.start.slice(0,2))*60 + Number(s.start.slice(3));
  return a.date === b.date && minutes(a) < minutes(b) + b.hours*60 && minutes(b) < minutes(a) + a.hours*60;
}

export function sumHours(subject: Subject, dates?: readonly string[]): number {
  const values = dates ? dates.map(date => subject.hours[date]) : Object.values(subject.hours);
  return round(values.reduce<number>((sum, value) => sum + (value ?? 0), 0));
}

export function round(value: number): number { return Math.round(value * 100) / 100; }

// UTC arithmetic prevents day shifts around Swiss daylight-saving transitions.
export function addDays(iso: string, offset: number): string {
  const date = new Date(iso + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

export function mondayOf(iso: string): string {
  const weekday = new Date(iso + 'T12:00:00Z').getUTCDay();
  return addDays(iso, -((weekday + 6) % 7));
}

export function weekDays(iso: string): string[] {
  return Array.from({length: 7}, (_, day) => addDays(mondayOf(iso), day));
}

export function dayLabel(iso: string, options: Intl.DateTimeFormatOptions = {day:'numeric', month:'short'}): string {
  return new Intl.DateTimeFormat('en-GB', {...options, timeZone:'UTC'}).format(new Date(iso + 'T12:00:00Z'));
}

export function dailyTotal(subjects: readonly Subject[], date: string): number {
  return round(subjects.reduce((sum, subject) => sum + (subject.hours[date] ?? 0), 0));
}

export function isValidDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
}

/** An exam time is either unknown, or a complete range within its calendar date. */
export function validExamTimes(start: unknown, end: unknown): boolean {
  return start == null && end == null || typeof start === 'string' && typeof end === 'string'
    && /^([01]\d|2[0-3]):[0-5]\d$/.test(start) && /^([01]\d|2[0-3]):[0-5]\d$/.test(end) && start < end;
}

export function validateData(value: unknown): value is StudyData {
  if (!value || typeof value !== 'object') return false;
  const d = value as StudyData;
  if (d.version !== 1 || typeof d.semester !== 'string' || !isValidDate(d.referenceDate)
    || !Array.isArray(d.dates) || !d.dates.length || d.dates.length > 730
    || !d.dates.every(isValidDate) || new Set(d.dates).size !== d.dates.length
    || d.dates.some((date, i) => i > 0 && date <= d.dates[i-1]) || !d.dates.includes(d.referenceDate)
    || !Array.isArray(d.subjects) || d.subjects.length > 50
    || !Array.isArray(d.anki) || d.anki.length > 100 || typeof d.notes !== 'string') return false;
  if (new Set(d.subjects.map(s => s?.id)).size !== d.subjects.length) return false;
  if (d.examSession && (!isValidDate(d.examSession.start) || !isValidDate(d.examSession.end)
    || d.examSession.start > d.examSession.end || !d.dates.includes(d.examSession.start) || !d.dates.includes(d.examSession.end))) return false;
  if (d.sessions !== undefined && (!Array.isArray(d.sessions) || d.sessions.length > 10000
    || !d.sessions.every(s => validSession(s, d)) || new Set(d.sessions.map(s => s.id)).size !== d.sessions.length
    || d.sessions.some((s,i) => d.sessions!.slice(i+1).some(other => sessionsOverlap(s,other))))) return false;
  return d.subjects.every(s => s && typeof s.id === 'string' && /^[a-z0-9-]+$/.test(s.id)
    && typeof s.name === 'string' && s.name.length > 0 && s.name.length < 200
    && typeof s.shortName === 'string' && s.shortName.length < 200
    && /^#[0-9a-fA-F]{6}$/.test(s.color)
    && Number.isFinite(s.targetHours) && s.targetHours >= 0 && s.targetHours <= 5000
    && isValidDate(s.examDate) && validExamTimes(s.examStart, s.examEnd) && typeof s.completed === 'boolean'
    && typeof s.nextAction === 'string' && s.nextAction.length <= 1000
    && (s.ects === undefined || (Number.isFinite(s.ects) && s.ects >= 0 && s.ects <= 60))
    && (s.lectureId === undefined || (typeof s.lectureId === 'string' && s.lectureId.length <= 100))
    && (s.homepage === undefined || (typeof s.homepage === 'string' && (!s.homepage || safeHomepage(s.homepage))))
    && !!s.hours && typeof s.hours === 'object' && !Array.isArray(s.hours)
    && Object.keys(s.hours).every(key => d.dates.includes(key))
    && Object.values(s.hours).every(h => h === null || (typeof h === 'number' && Number.isFinite(h) && h >= 0 && h <= 24)))
    && d.dates.every(date => dailyTotal(d.subjects, date) <= 24)
    && d.anki.every(a => a && typeof a.name === 'string' && a.name.length < 200
      && (a.subjectId === undefined || d.subjects.some(s => s.id === a.subjectId))
      && [a.total,a.mature,a.learned,a.left].every(n => Number.isInteger(n) && n >= 0)
      && a.mature + a.learned + a.left === a.total);
}
