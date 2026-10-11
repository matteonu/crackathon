import type { PlannedSession, StudyData, Subject } from './study';

/* Schedule statistics, computed from the study plan alone (recorded hours per subject and day,
   planned sessions, targets and exam dates). Pure functions, so they are unit-tested and the
   component only renders. No value imports from other models: the node test runner wants
   './x.ts' paths and the Angular compiler refuses them, so the date helpers live here. */

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function round1(value: number): number { return Math.round(value * 10) / 10; }

/** Fit the viewport with 8–24 px bars. Below 8 px, scroll; above 24 px, grow height
 * proportionally and give the extra horizontal space to the gaps between days. */
export function dailyChartLayout(dayCount: number, viewportWidth: number): {width: number; height: number; dayWidth: number; barWidth: number} {
  const count = Math.max(1, dayCount);
  const width = Math.max(viewportWidth, 34 + count * 14 + 8);
  const dayWidth = (width - 34 - 8) / count;
  return {width, dayWidth, barWidth: Math.min(24, dayWidth - 6), height: 170 * Math.max(1, dayWidth / 30)};
}

export function addDay(iso: string, offset: number): string {
  const d = new Date(iso + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}

/** 0 = Monday ... 6 = Sunday. */
export function weekdayIndex(iso: string): number {
  return (new Date(iso + 'T12:00:00Z').getUTCDay() + 6) % 7;
}

export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to + 'T12:00:00Z') - Date.parse(from + 'T12:00:00Z')) / 86_400_000);
}

export function recordedOn(subjects: readonly Subject[], date: string): number {
  return subjects.reduce((sum, s) => sum + (s.hours[date] ?? 0), 0);
}

export function recordedTotal(subject: Subject, upTo?: string): number {
  return Object.entries(subject.hours).reduce((sum, [date, h]) => sum + ((!upTo || date <= upTo) ? (h ?? 0) : 0), 0);
}

/** The last day that counts as "so far": today clamped to the phase, or the last recorded day
 *  if that is later (demo data recorded ahead of the calendar still reads as progress). */
export function asOfDate(data: StudyData, today: string): string {
  const start = data.dates[0], end = data.dates[data.dates.length - 1];
  const clamped = today < start ? start : today > end ? end : today;
  const lastRecorded = data.subjects.flatMap(s => Object.entries(s.hours).filter(([, h]) => h != null).map(([d]) => d)).sort().at(-1);
  return lastRecorded && lastRecorded > clamped ? lastRecorded : clamped;
}

export interface DayPoint {
  date: string; recorded: number; planned: number; bySubject: Record<string, number>; weekday: number;
  /** A deliberate day off: something was recorded for the day, but zero hours. The schedule
   *  distinguishes "no record" from "0 recorded", and the hours editor says so. */
  rest: boolean;
}

/** One point per phase day: hours recorded (per subject too) and hours planned in sessions. */
export function dailySeries(data: StudyData): DayPoint[] {
  const planned = new Map<string, number>();
  for (const s of data.sessions ?? []) planned.set(s.date, (planned.get(s.date) ?? 0) + s.hours);
  return data.dates.map(date => {
    const bySubject: Record<string, number> = {};
    for (const s of data.subjects) if (s.hours[date]) bySubject[s.id] = s.hours[date]!;
    const recorded = round1(recordedOn(data.subjects, date));
    const anyRecord = data.subjects.some(s => s.hours[date] != null);
    return {date, recorded, planned: round1(planned.get(date) ?? 0), bySubject, weekday: weekdayIndex(date), rest: anyRecord && recorded === 0};
  });
}

export interface ActivityDay { date: string; hours: number; level: number; recorded: boolean; }
export interface ActivityWeek { start: string; month: string; days: (ActivityDay | null)[]; }

/** Monday-first calendar columns, padded outside the study phase. Colors use fixed hour bands. */
export function activityWeeks(data: StudyData): ActivityWeek[] {
  if (!data.dates.length) return [];
  const days = new Map(data.dates.map(date => {
    const hours = round1(recordedOn(data.subjects, date));
    return [date, {date, hours, level: hours <= 0 ? 0 : hours < 2 ? 1 : hours < 4 ? 2 : hours < 6 ? 3 : 4,
      recorded: data.subjects.some(subject => subject.hours[date] != null)}] as const;
  }));
  const weeks: ActivityWeek[] = [];
  let previousMonth = '';
  for (let start = addDay(data.dates[0], -weekdayIndex(data.dates[0])); start <= data.dates.at(-1)!; start = addDay(start, 7)) {
    const column = Array.from({length: 7}, (_, i) => days.get(addDay(start, i)) ?? null);
    const first = column.find(day => day !== null)!;
    const monthKey = first.date.slice(0, 7);
    const month = monthKey !== previousMonth ? new Intl.DateTimeFormat('en-GB', {month: 'short', timeZone: 'UTC'}).format(new Date(first.date + 'T12:00:00Z')) : '';
    previousMonth = monthKey;
    weeks.push({start, month, days: column});
  }
  return weeks;
}

export interface WeekPoint { start: string; recorded: number; planned: number; target: number; }

/** Hours per calendar week (Monday-based) with the even pace that would hit the overall target. */
export function weeklySeries(data: StudyData, days = dailySeries(data)): WeekPoint[] {
  const weeks = new Map<string, WeekPoint>();
  for (const day of days) {
    const start = addDay(day.date, -day.weekday);
    const week = weeks.get(start) ?? {start, recorded: 0, planned: 0, target: 0};
    week.recorded += day.recorded; week.planned += day.planned;
    weeks.set(start, week);
  }
  const target = data.subjects.reduce((sum, s) => sum + s.targetHours, 0);
  const perDay = data.dates.length ? target / data.dates.length : 0;
  for (const week of weeks.values()) {
    const inPhase = days.filter(d => addDay(d.date, -d.weekday) === week.start).length;
    week.target = round1(perDay * inPhase); week.recorded = round1(week.recorded); week.planned = round1(week.planned);
  }
  return [...weeks.values()].sort((a, b) => a.start.localeCompare(b.start));
}

export interface Pace {
  asOf: string; elapsedDays: number; totalDays: number; remainingDays: number;
  recorded: number; target: number; expected: number;     // expected = target * elapsed share
  projected: number;                                      // at the current daily rate
  neededPerDay: number;                                   // to still reach the target
  ratePerDay: number;                                     // recorded / elapsed days
}

/** Are we ahead or behind an even pace, and what would it take from here. */
export function pace(data: StudyData, asOf: string): Pace {
  const start = data.dates[0], end = data.dates[data.dates.length - 1];
  const totalDays = data.dates.length;
  const elapsedDays = Math.min(totalDays, Math.max(0, daysBetween(start, asOf) + 1));
  const remainingDays = Math.max(0, daysBetween(asOf, end));
  const recorded = round1(data.subjects.reduce((sum, s) => sum + recordedTotal(s, asOf), 0));
  const target = round1(data.subjects.reduce((sum, s) => sum + s.targetHours, 0));
  const ratePerDay = elapsedDays ? recorded / elapsedDays : 0;
  return {asOf, elapsedDays, totalDays, remainingDays, recorded, target,
    expected: round1(totalDays ? target * elapsedDays / totalDays : 0),
    projected: round1(ratePerDay * totalDays),
    neededPerDay: round1(remainingDays ? Math.max(0, target - recorded) / remainingDays : 0),
    ratePerDay: round1(ratePerDay)};
}

export interface SubjectStat {
  subject: Subject; recorded: number; target: number; remaining: number; percent: number;
  share: number; targetShare: number;                     // of all recorded / of all targets
  daysToExam: number; neededPerDay: number; status: 'done' | 'on-track' | 'behind' | 'at-risk';
  plannedAhead: number;                                   // hours in sessions after asOf
}

/** Per subject: progress against target, pace needed before its exam, and whether that is realistic. */
export function subjectStats(data: StudyData, asOf: string): SubjectStat[] {
  const totalRecorded = data.subjects.reduce((sum, s) => sum + recordedTotal(s, asOf), 0);
  const totalTarget = data.subjects.reduce((sum, s) => sum + s.targetHours, 0);
  const sessions = data.sessions ?? [];
  return data.subjects.map(subject => {
    const recorded = round1(recordedTotal(subject, asOf));
    const remaining = round1(Math.max(0, subject.targetHours - recorded));
    const daysToExam = daysBetween(asOf, subject.examDate);
    const neededPerDay = daysToExam > 0 ? round1(remaining / daysToExam) : remaining > 0 ? Infinity : 0;
    const plannedAhead = round1(sessions.filter(s => s.subjectId === subject.id && s.date > asOf).reduce((sum, s) => sum + s.hours, 0));
    let status: SubjectStat['status'] = 'on-track';
    if (subject.completed || remaining === 0) status = 'done';
    else if (daysToExam <= 0 || neededPerDay > 6) status = 'at-risk';
    else if (neededPerDay > 3.5) status = 'behind';
    return {subject, recorded, target: subject.targetHours, remaining,
      percent: subject.targetHours ? Math.min(100, Math.round(recorded / subject.targetHours * 100)) : 0,
      share: totalRecorded ? recorded / totalRecorded : 0, targetShare: totalTarget ? subject.targetHours / totalTarget : 0,
      daysToExam, neededPerDay, status, plannedAhead};
  }).sort((a, b) => a.subject.examDate.localeCompare(b.subject.examDate));
}

export interface Consistency {
  recordedDays: number; restDays: number; elapsedDays: number; ratio: number;
  currentStreak: number; longestStreak: number; longestBreak: number;
  averagePerRecordedDay: number; medianPerRecordedDay: number; bestDay: DayPoint | null;
}

/** How regular the studying is: streaks, gaps, and a typical day. A streak is consecutive
 *  study days; a rest day (recorded as 0) neither extends nor breaks it, only a day with no
 *  record at all does. Breaks count unrecorded days only. */
export function consistency(days: DayPoint[], asOf: string): Consistency {
  const elapsed = days.filter(d => d.date <= asOf);
  const recorded = elapsed.filter(d => d.recorded > 0);
  let current = 0, longest = 0, run = 0, longestBreak = 0, gap = 0;
  for (const day of elapsed) {
    if (day.recorded > 0) { run++; gap = 0; }
    else if (day.rest) { gap = 0; }
    else { run = 0; gap++; }
    longest = Math.max(longest, run); longestBreak = Math.max(longestBreak, gap);
  }
  for (let i = elapsed.length - 1; i >= 0 && (elapsed[i].recorded > 0 || elapsed[i].rest); i--) if (elapsed[i].recorded > 0) current++;
  const values = recorded.map(d => d.recorded).sort((a, b) => a - b);
  const median = values.length ? (values.length % 2 ? values[(values.length - 1) / 2] : (values[values.length / 2 - 1] + values[values.length / 2]) / 2) : 0;
  return {recordedDays: recorded.length, restDays: elapsed.filter(d => d.rest).length, elapsedDays: elapsed.length, ratio: elapsed.length ? recorded.length / elapsed.length : 0,
    currentStreak: current, longestStreak: longest, longestBreak,
    averagePerRecordedDay: round1(recorded.length ? values.reduce((a, b) => a + b, 0) / recorded.length : 0),
    medianPerRecordedDay: round1(median), bestDay: recorded.length ? recorded.reduce((best, d) => d.recorded > best.recorded ? d : best) : null};
}

/** Average recorded hours per weekday over the elapsed days (days with no record count as 0). */
export function weekdayProfile(days: DayPoint[], asOf: string): number[] {
  const sums = Array(7).fill(0), counts = Array(7).fill(0);
  for (const day of days) if (day.date <= asOf) { sums[day.weekday] += day.recorded; counts[day.weekday]++; }
  return sums.map((sum, i) => round1(counts[i] ? sum / counts[i] : 0));
}

export interface PlanAdherence { plannedDays: number; keptDays: number; plannedHours: number; recordedOnPlannedDays: number; ratio: number; }

/** On days with planned sessions up to asOf: how much of the plan turned into recorded hours. */
export function planAdherence(days: DayPoint[], asOf: string): PlanAdherence {
  const planned = days.filter(d => d.date <= asOf && d.planned > 0);
  const plannedHours = round1(planned.reduce((sum, d) => sum + d.planned, 0));
  const recordedOnPlannedDays = round1(planned.reduce((sum, d) => sum + Math.min(d.recorded, d.planned), 0));
  return {plannedDays: planned.length, keptDays: planned.filter(d => d.recorded > 0).length, plannedHours, recordedOnPlannedDays,
    ratio: plannedHours ? recordedOnPlannedDays / plannedHours : 0};
}

export interface PlanDeviation {
  planned: number; recorded: number; delta: number;
  /** Fixed -20 to +20 hour range; larger gaps stay at the nearest end. */
  position: number;
  tone: 'success' | 'strong-success' | 'warning' | 'danger' | 'neutral';
  /** Color intensity on the fixed range, from 0 to 100 percent. */
  strength: number;
}

/** Recorded versus calendar hours so far, including study on unplanned days.
 * Shortfalls move from yellow to red; excess hours move from green to dark green. */
export function planDeviation(days: DayPoint[], asOf: string): PlanDeviation {
  const elapsed = days.filter(day => day.date <= asOf);
  const planned = round1(elapsed.reduce((sum, day) => sum + day.planned, 0));
  const recorded = round1(elapsed.reduce((sum, day) => sum + day.recorded, 0));
  const delta = round1(recorded - planned);
  const position = Math.max(0, Math.min(100, 50 + delta * 2.5));
  const strength = Math.min(100, Math.abs(delta) * 5);
  const tone = planned === 0 || delta === 0 ? 'neutral' : delta < 0
    ? delta < -10 ? 'danger' : 'warning'
    : delta > 10 ? 'strong-success' : 'success';
  return {planned, recorded, delta, position, tone, strength};
}

export interface PlanVsRecordedDay { date: string; planned: number; recorded: number; }

/** One subject's planned and recorded hours for the `count` study-phase days up to asOf
 *  (fewer when the phase started more recently). */
export function recentPlanVsRecorded(data: StudyData, subjectId: string, asOf: string, count = 7): PlanVsRecordedDay[] {
  const subject = data.subjects.find(s => s.id === subjectId);
  if (!subject) return [];
  return data.dates.filter(d => d <= asOf).slice(-count).map(date => ({
    date,
    planned: round1((data.sessions ?? []).filter(s => s.subjectId === subjectId && s.date === date).reduce((sum, s) => sum + s.hours, 0)),
    recorded: round1(subject.hours[date] ?? 0),
  }));
}

/** Hours already in the calendar after asOf, per day, and whether they cover what is still needed. */
export function plannedAhead(data: StudyData, asOf: string): { hours: number; days: number; perDay: number } {
  const ahead = (data.sessions ?? []).filter(s => s.date > asOf);
  const days = new Set(ahead.map(s => s.date)).size;
  const hours = round1(ahead.reduce((sum, s) => sum + s.hours, 0));
  return {hours, days, perDay: round1(days ? hours / days : 0)};
}

/** Largest gap between a subject's share of time and its share of the targets, as a signed delta. */
export function balanceDelta(stats: SubjectStat[]): { subject: Subject; delta: number; recordedShare: number; targetShare: number } | null {
  if (!stats.length || !stats.some(s => s.recorded > 0) || !stats.some(s => s.target > 0)) return null;
  const worst = stats.reduce((w, s) => Math.abs(s.share - s.targetShare) > Math.abs(w.share - w.targetShare) ? s : w);
  return {subject: worst.subject, delta: round1((worst.share - worst.targetShare) * 100),
    recordedShare: round1(worst.share * 100), targetShare: round1(worst.targetShare * 100)};
}

export function sessionsOf(data: StudyData): PlannedSession[] { return data.sessions ?? []; }
