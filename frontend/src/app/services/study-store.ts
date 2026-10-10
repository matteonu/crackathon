import { Injectable, computed, signal } from '@angular/core';
import { StudyData, Subject, PlannedSession, validSession, sessionsOverlap, addDays, dailyTotal, mondayOf, round, sumHours, validateData, weekDays } from '../models/study';
import { CourseHit, GeneratedPlan, Plan, PlanBlock, PlanSubject, Preferences, SemesterOption, Semesters,
  courseIdOf, emptyData, planToData, studyHours, visibleBlock } from '../models/semester';

/** The habits of a semester nobody has configured, mirroring the server's defaults. */
const DEFAULT_PREFERENCES: Preferences = {dayStart:'08:00', dayEnd:'20:00', lunch:['12:00','13:00'],
  dinner:['18:00','19:00'], studyBlockSize:60, studyHoursPerWeek:null, alpha:.3, beta:5, daysOff:[]};

/** The scheduler fields of one course that the setup form may change. */
export type CoursePlanPatch = Partial<{priority:number; difficulty:number|null; maxStudyHours:number|null;
  lecturePerWeek:number|null; examDate:string; targetHours:number}>;

const today = () => new Date().toISOString().slice(0, 10);

/** The study plan of the current semester, kept on the server (see backend/planner.py).
 *  This is the in-memory copy the pages read. A change shows at once, is sent to the server
 *  in order, and if the server refuses it the plan is reloaded from the server. */
@Injectable({providedIn:'root'})
export class StudyStore {
  readonly persistence = signal('Loading your plan…');
  readonly loaded = signal(false);
  readonly loadError = signal('');
  readonly semkez = signal('');
  /** The semesters the user can switch to, and today's semester. */
  readonly semesters = signal<SemesterOption[]>([]);
  readonly currentSemkez = signal('');
  /** Whether courses can be added to the shown semester (it is in the course catalogue). */
  readonly inCatalogue = computed(() => this.semesters().find(s => s.semkez === this.semkez())?.inCatalogue ?? true);
  private readonly state = signal<StudyData>(emptyData(today()));
  readonly data = this.state.asReadonly();
  readonly subjects = computed(() => this.data().subjects);
  readonly dates = computed(() => this.data().dates);
  readonly examSession = computed(() => this.data().examSession ?? {start:this.dates()[0], end:this.dates().at(-1)!});
  readonly sessions = computed(() => this.data().sessions ?? []);
  readonly totalHours = computed(() => round(this.subjects().reduce((s, subject) => s + sumHours(subject), 0)));
  readonly targetHours = computed(() => round(this.subjects().reduce((s, subject) => s + subject.targetHours, 0)));
  readonly completedCount = computed(() => this.subjects().filter(s => s.completed).length);
  readonly recordedDays = computed(() => this.dates().filter(date => this.subjects().some(s => s.hours[date] != null)).length);
  readonly exams = computed(() => [...this.subjects()].sort((a,b) => a.examDate.localeCompare(b.examDate)));
  readonly weekStart = signal(mondayOf(this.data().referenceDate));
  readonly week = computed(() => weekDays(this.weekStart()));
  readonly weekHours = computed(() => round(this.subjects().reduce((s,subject) => s + sumHours(subject,this.week()), 0)));
  readonly firstWeek = computed(() => mondayOf(this.dates()[0]));
  readonly lastWeek = computed(() => mondayOf(this.dates().at(-1)!));
  readonly canGoBack = computed(() => this.weekStart() > this.firstWeek());
  readonly canGoNext = computed(() => this.weekStart() < this.lastWeek());
  readonly editor = signal<{subjectId:string,date:string} | null>(null);
  /** The courses as the server describes them, scheduler fields included. */
  readonly planSubjects = signal<PlanSubject[]>([]);
  readonly preferences = signal<Preferences>(DEFAULT_PREFERENCES);
  /** The generated schedule, or null while none has been generated. */
  readonly generatedPlan = signal<GeneratedPlan | null>(null);
  readonly planError = signal('');
  readonly generating = signal(false);
  readonly planHours = computed(() => studyHours(this.generatedPlan()?.blocks ?? []));
  readonly notice = signal('');
  private noticeTimer?: ReturnType<typeof setTimeout>;
  private writes: Promise<unknown> = Promise.resolve();
  private pending = 0;

  constructor() { void this.load(); }

  private async request<T>(url:string, init?:RequestInit):Promise<T> {
    let response:Response;
    try { response = await fetch(url, {cache:'no-store', ...init}); }
    catch { throw new Error('Cannot reach the server. Check your connection and retry.'); }
    let data:unknown = null;
    try { data = await response.json(); } catch { /* Non-JSON errors have no body. */ }
    if (!response.ok) throw new Error(typeof (data as {error?:unknown})?.error === 'string' ? (data as {error:string}).error : 'The server could not save that change. Please retry.');
    return data as T;
  }
  private json(method:string, body:unknown):RequestInit {
    return {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
  }

  /** Loads the selected semester's plan (the server remembers the choice). Keeps the shown week
   *  when it is still in range, unless `newSemester` says the user just switched. */
  async load(newSemester=false):Promise<void> {
    try {
      const semesters = await this.request<Semesters>('/api/semesters');
      this.semesters.set(semesters.available); this.currentSemkez.set(semesters.current);
      if (!this.semkez()) this.semkez.set(semesters.selected);
      const plan = await this.request<Plan>(`/api/semesters/${this.semkez()}/plan`);
      const data = planToData(plan, today());
      const first = !this.loaded() || newSemester;
      this.state.set(data);
      this.planSubjects.set(plan.subjects);
      this.preferences.set(plan.preferences ?? DEFAULT_PREFERENCES);
      this.generatedPlan.set(plan.plan);
      if (first || this.weekStart() < mondayOf(data.dates[0]) || this.weekStart() > mondayOf(data.dates.at(-1)!)) this.weekStart.set(mondayOf(data.referenceDate));
      this.loaded.set(true); this.loadError.set(''); this.persistence.set('Saved to your account');
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not load your study plan.';
      this.loadError.set(message); this.persistence.set(`Not loaded: ${message}`);
    }
  }

  /** Sends a change after the ones before it. On failure the server's version is reloaded. */
  private write(url:string, init:RequestInit):Promise<void> {
    this.pending++; this.persistence.set('Saving…');
    const run = this.writes.then(async () => {
      try { await this.request(url, init); }
      catch (e) {
        const message = e instanceof Error ? e.message : 'Could not save that change.';
        this.announce(`Not saved: ${message}`);
        await this.load();
        throw e;
      } finally {
        if (--this.pending === 0 && !this.loadError()) this.persistence.set('Saved to your account');
      }
    });
    this.writes = run.catch(() => undefined);
    return run.catch(() => undefined);
  }
  private courseUrl(subjectId:string):string {
    const courseId = courseIdOf(subjectId);
    if (courseId === null) throw new Error('This subject is not a course of yours.');
    return `/api/semesters/${this.semkez()}/courses/${courseId}`;
  }

  hours(subject:Subject, dates?:readonly string[]):number { return sumHours(subject,dates); }
  daily(date:string):number { return dailyTotal(this.subjects(),date); }
  remaining(subject:Subject):number { return round(subject.targetHours - sumHours(subject)); }
  progress(subject:Subject):number { return subject.targetHours ? Math.min(100, sumHours(subject)/subject.targetHours*100) : 0; }

  moveWeek(offset:number):void {
    const next=addDays(this.weekStart(),7*offset);
    if(next >= this.firstWeek() && next <= this.lastWeek()) this.weekStart.set(next);
  }
  setWeek(date:string):void {
    const week=mondayOf(date);
    if(week >= this.firstWeek() && week <= this.lastWeek()) this.weekStart.set(week);
  }
  openEditor(subjectId=this.subjects()[0]?.id,date=this.week().find(d=>this.dates().includes(d))??this.examSession().start):void {
    if(!subjectId){this.announce('Add a course first, with + next to Your subjects.');return;}
    this.editor.set({subjectId,date});
  }
  setHours(subjectId:string,date:string,hours:number|null):void {
    if(date < this.examSession().start || date > this.examSession().end) throw new Error('Choose a date within this exam session.');
    if(!this.dates().includes(date) || !this.subjects().some(s=>s.id===subjectId)) throw new Error('Choose a subject and date in this study phase.');
    if(hours !== null && (!Number.isFinite(hours) || hours < 0 || hours > 24)) throw new Error('Enter a number between 0 and 24 hours.');
    const others=this.subjects().filter(s=>s.id!==subjectId);
    if(round(dailyTotal(others,date)+(hours??0))>24) throw new Error('The combined study time for this day cannot exceed 24 hours.');
    const url=`${this.courseUrl(subjectId)}/hours/${date}`;
    const value=hours===null?null:round(hours);
    this.state.update(d=>({...d,subjects:d.subjects.map(s=>{
      if(s.id!==subjectId) return s;
      const next={...s.hours}; if(value===null) delete next[date]; else next[date]=value;
      return {...s,hours:next};
    })}));
    this.editor.set(null);
    this.announce(hours===null ? 'Recorded hours cleared.' : 'Study hours saved. Your analytics are up to date.');
    void this.write(url,this.json('PUT',{hours:value}));
  }
  /** ECTS, lecture ID and homepage come from the VVZ and are not the user's to change. */
  updateSubject(id:string,patch:Partial<Pick<Subject,'targetHours'|'examDate'|'nextAction'|'completed'>>):void {
    const data={...this.data(),subjects:this.subjects().map(s=>s.id===id?{...s,...patch}:s)};
    if(!validateData(data)) throw new Error('Check the target hours, exam date, and next action.');
    const url=this.courseUrl(id);
    this.state.set(data); this.announce('Subject changes saved.');
    void this.write(url,this.json('PATCH',patch));
  }
  /** The slots the calendar shows on one day, earliest first. The scheduler's own lunch and
   *  dinner are left out; a break the user drew is shown. */
  planOn(date:string):PlanBlock[] {
    return (this.generatedPlan()?.blocks ?? []).filter(block => block.date === date && visibleBlock(block));
  }

  /** Draw a slot. Generated slots under it give way; the server refuses an overlap with yours. */
  createSlot(slot:{date:string; start:string; end:string; kind:'course'|'break'; courseId?:number}):Promise<boolean> {
    return this.slotRequest(`/api/semesters/${this.semkez()}/plan/blocks`, this.json('POST', slot));
  }
  /** Move or resize a slot. It becomes the user's own, so regenerating keeps it. */
  moveSlot(id:number, patch:{date?:string; start?:string; end?:string}):Promise<boolean> {
    const plan=this.generatedPlan();
    if(plan)this.generatedPlan.set({...plan,blocks:plan.blocks.map(b=>b.id===id?{...b,...patch,source:'manual' as const}:b)});
    return this.slotRequest(`/api/semesters/${this.semkez()}/plan/blocks/${id}`, this.json('PATCH', patch));
  }
  deleteSlot(id:number):Promise<boolean> {
    const plan=this.generatedPlan();
    if(plan)this.generatedPlan.set({...plan,blocks:plan.blocks.filter(b=>b.id!==id)});
    return this.slotRequest(`/api/semesters/${this.semkez()}/plan/blocks/${id}`, {method:'DELETE'});
  }
  /** Send a slot change after the ones before it, then take the server's plan and targets. */
  private async slotRequest(url:string, init:RequestInit):Promise<boolean> {
    await this.writes;
    try {
      this.generatedPlan.set(await this.request<GeneratedPlan | null>(url, init));
      await this.load();          // target hours follow the slots
      return true;
    } catch (e) {
      this.announce(e instanceof Error ? e.message : 'Could not change that slot.');
      await this.load();
      return false;
    }
  }
  /** Hours the plan asks for on one day, across every course. */
  plannedDaily(date:string):number {
    return studyHours((this.generatedPlan()?.blocks ?? []).filter(block => block.date === date));
  }
  /** Hours of study the plan holds for a subject, over the given dates or all of them. */
  planHoursFor(subjectId:string, dates?:readonly string[]):number {
    return studyHours((this.generatedPlan()?.blocks ?? []).filter(block =>
      block.subjectId === subjectId && (!dates || dates.includes(block.date))));
  }

  /** Ask the server for a schedule. `dryRun` previews it without storing anything. */
  async generate(options:{fromDate?:string; dryRun?:boolean} = {}):Promise<GeneratedPlan | null> {
    await this.writes;        // Let a queued change to a course land before planning around it.
    this.generating.set(true); this.planError.set('');
    try {
      const plan = await this.request<GeneratedPlan>(
        `/api/semesters/${this.semkez()}/plan/generate`, this.json('POST', options));
      if (!options.dryRun) { this.generatedPlan.set(plan); this.announce('Your schedule proposal is saved.'); }
      return plan;
    } catch (e) {
      this.planError.set(e instanceof Error ? e.message : 'Could not generate a schedule.');
      return null;
    } finally { this.generating.set(false); }
  }

  /** Save study habits. Only the fields given are changed. */
  async savePreferences(patch:Partial<Preferences>):Promise<boolean> {
    this.planError.set('');
    try {
      this.preferences.set(await this.request<Preferences>(
        `/api/semesters/${this.semkez()}/preferences`, this.json('PUT', patch)));
      this.announce('Study habits saved.');
      return true;
    } catch (e) {
      this.planError.set(e instanceof Error ? e.message : 'Could not save your habits.');
      return false;
    }
  }

  /** Save what the scheduler should know about one course. */
  async updateCoursePlan(courseId:number, patch:CoursePlanPatch):Promise<boolean> {
    this.planError.set('');
    try {
      const subject = await this.request<PlanSubject>(
        `/api/semesters/${this.semkez()}/courses/${courseId}`, this.json('PATCH', patch));
      this.planSubjects.update(list => list.map(s => s.courseId === courseId ? subject : s));
      // Keep the copy the pages read in step with what came back.
      this.state.update(d => ({...d, subjects: d.subjects.map(s => s.courseId === courseId
        ? {...s, examDate:subject.examDate, targetHours:subject.targetHours, completed:subject.completed} : s)}));
      return true;
    } catch (e) {
      this.planError.set(e instanceof Error ? e.message : 'Could not save that course.');
      return false;
    }
  }

  toggleDone(id:string):void {
    const subject=this.subjects().find(s=>s.id===id);
    if(subject) this.updateSubject(id,{completed:!subject.completed});
  }
  /** Anki decks have no source yet (the old sample's snapshot is gone), so there is nothing to link. */
  linkDeck(name:string,subjectId:string):void {
    if(subjectId && !this.subjects().some(s=>s.id===subjectId)) return;
    this.state.update(d=>({...d,anki:d.anki.map(a=>a.name===name?{...a,subjectId:subjectId || undefined}:a)}));
  }
  saveSessions(sessions:PlannedSession[]):void {
    if(!sessions.every(s=>validSession(s,this.data())) || new Set(sessions.map(s=>s.id)).size!==sessions.length)
      throw new Error('Check the subject, date, start time, and duration. Sessions must end by midnight.');
    if(sessions.some((s,i)=>sessions.slice(i+1).some(other=>sessionsOverlap(s,other))))
      throw new Error('Study sessions cannot overlap. Choose another time.');
    this.state.update(d=>({...d,sessions}));
    this.announce('Planned sessions saved.');
    void this.write(`/api/semesters/${this.semkez()}/sessions`,this.json('PUT',sessions));
  }

  /** Shows another semester. Pending changes are saved first; the choice is stored on the server. */
  async selectSemester(semkez:string):Promise<void> {
    if (semkez === this.semkez()) return;
    await this.writes;
    try { await this.request('/api/semesters/selected', this.json('PUT', {semkez})); }
    catch (e) { this.announce(e instanceof Error ? e.message : 'Could not switch the semester.'); return; }
    this.editor.set(null);
    this.semkez.set(semkez);
    await this.load(true);
  }

  /** Courses offered this semester whose code or title contains q (at least 2 characters). */
  searchCourses(q:string):Promise<CourseHit[]> {
    return this.request<CourseHit[]>(`/api/courses?semkez=${encodeURIComponent(this.semkez())}&q=${encodeURIComponent(q)}&limit=20`);
  }
  /** Adds a course to this semester. It becomes a subject once the plan is reloaded. */
  async addCourse(hit:CourseHit):Promise<void> {
    await this.request(`/api/semesters/${this.semkez()}/courses`,this.json('POST',{courseId:hit.id}));
    await this.load();
    this.announce(`${hit.title} added to ${this.data().semester}.`);
  }
  /** Removes a course from this semester, together with its recorded hours and planned sessions. */
  async removeCourse(subject:Subject):Promise<void> {
    await this.writes;
    await this.request(this.courseUrl(subject.id),{method:'DELETE'});
    await this.load();
    this.announce(`${subject.name} removed from ${this.data().semester}.`);
  }

  announce(message:string):void {
    clearTimeout(this.noticeTimer); this.notice.set(message);
    this.noticeTimer=setTimeout(()=>this.notice.set(''),5000);
  }
  exportData():void {
    const url=URL.createObjectURL(new Blob([JSON.stringify(this.data(),null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=`studyphase-${this.data().semester||'plan'}.json`;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000); this.announce('Your study data has been exported.');
  }
}
