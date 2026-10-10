import { Injectable, computed, effect, signal } from '@angular/core';
import seed from '../data/study-data.json';
import { StudyData, Subject, PlannedSession, validSession, sessionsOverlap, addDays, dailyTotal, mondayOf, round, sumHours, validateData, weekDays } from '../models/study';

const STORAGE_KEY = 'studyphase-angular-v1';

@Injectable({providedIn:'root'})
export class StudyStore {
  readonly persistence = signal('Saved on this device');
  private readonly state = signal<StudyData>(this.load());
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
  readonly notice = signal('');
  private noticeTimer?: ReturnType<typeof setTimeout>;

  constructor() {
    effect(() => {
      const data = this.state();
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); }
      catch { this.persistence.set('Changes are temporary; use Export to keep them'); }
    });
  }

  private load(): StudyData {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) { const parsed:unknown = JSON.parse(raw); if (validateData(parsed)) return parsed; }
    } catch { /* Missing, unavailable or invalid storage falls back to the sample. */ }
    return structuredClone(seed) as StudyData;
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
  openEditor(subjectId=this.subjects()[0].id,date=this.week().find(d=>this.dates().includes(d))!):void {
    this.editor.set({subjectId,date});
  }
  setHours(subjectId:string,date:string,hours:number|null):void {
    if(date < this.examSession().start || date > this.examSession().end) throw new Error('Choose a date within this exam session.');
    if(!this.dates().includes(date) || !this.subjects().some(s=>s.id===subjectId)) throw new Error('Choose a subject and date in this study phase.');
    if(hours !== null && (!Number.isFinite(hours) || hours < 0 || hours > 24)) throw new Error('Enter a number between 0 and 24 hours.');
    const others=this.subjects().filter(s=>s.id!==subjectId);
    if(round(dailyTotal(others,date)+(hours??0))>24) throw new Error('The combined study time for this day cannot exceed 24 hours.');
    this.state.update(d=>({...d,subjects:d.subjects.map(s=>s.id===subjectId ? {...s,hours:{...s.hours,[date]:hours===null?null:round(hours)}} : s)}));
    this.editor.set(null);
    this.announce(hours===null ? 'Recorded hours cleared.' : 'Study hours saved. Your analytics are up to date.');
  }
  updateSubject(id:string,patch:Partial<Pick<Subject,'targetHours'|'examDate'|'nextAction'|'completed'|'ects'|'lectureId'|'homepage'>>):void {
    const data={...this.data(),subjects:this.subjects().map(s=>s.id===id?{...s,...patch}:s)};
    if(!validateData(data)) throw new Error('Check the target hours, exam date, and next action.');
    this.state.set(data); this.announce('Subject changes saved.');
  }
  toggleDone(id:string):void {
    this.state.update(d=>({...d,subjects:d.subjects.map(s=>s.id===id?{...s,completed:!s.completed}:s)}));
  }
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
  }
  announce(message:string):void {
    clearTimeout(this.noticeTimer); this.notice.set(message);
    this.noticeTimer=setTimeout(()=>this.notice.set(''),5000);
  }
  exportData():void {
    const url=URL.createObjectURL(new Blob([JSON.stringify(this.data(),null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='studyphase-data.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000); this.announce('Your study data has been exported.');
  }
  importData(value:unknown):void {
    if(!validateData(value)) throw new Error('This file is not valid Studyphase data. Import a JSON file created with Export data.');
    this.state.set(structuredClone(value)); this.weekStart.set(mondayOf(value.referenceDate));
    this.announce('Study data imported.');
  }
  reset():void {
    this.state.set(structuredClone(seed) as StudyData);
    this.weekStart.set(mondayOf(seed.referenceDate)); this.announce('The original HS24 sample has been restored.');
  }
}
