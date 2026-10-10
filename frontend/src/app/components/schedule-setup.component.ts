import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { StudyStore } from '../services/study-store';
import { DayOff, Preferences } from '../models/semester';
import { IconComponent } from '../shared/icon.component';

/** One course as the form edits it, before anything is sent. */
interface CourseDraft {courseId:number;name:string;color:string;examDate:string;priority:number;difficulty:number;maxStudyHours:number|null;}

const PRIORITIES=[{value:1,label:'1 — most important'},{value:2,label:'2'},{value:3,label:'3 — normal'},{value:4,label:'4'},{value:5,label:'5 — least important'}];
const DIFFICULTIES=[{value:1,label:'1 — easy'},{value:2,label:'2'},{value:3,label:'3 — normal'},{value:4,label:'4'},{value:5,label:'5 — hard'}];

/** Everything the scheduler needs from the user: their courses' weights and their habits.
 *  Opened before the first proposal, and from the calendar whenever they want to adjust it. */
@Component({selector:'app-schedule-setup',standalone:true,imports:[IconComponent],template:`
  <dialog #dialog class="edit-dialog schedule-setup-dialog" aria-labelledby="setup-title" (close)="error.set('')">
    <div class="dialog-top"><span class="eyebrow">BEFORE WE PLAN</span><button type="button" class="icon-button" aria-label="Close" (click)="dialog.close()"><app-icon name="close" /></button></div>
    <h2 id="setup-title">How do you want to study?</h2>
    <p class="muted">The schedule is built from this. ECTS and weekly lecture hours come from the course catalogue; what is below is yours.</p>

    <h3 class="setup-heading">Your courses</h3>
    @if(!courses().length){<p class="empty-state">No courses yet. Add one with + next to Your subjects.</p>}
    <div class="setup-courses">@for(course of courses();track course.courseId){
      <div class="setup-course">
        <div class="setup-course-name"><span class="subject-dot" [style.background]="course.color"></span><strong>{{course.name}}</strong></div>
        <div class="form-grid setup-course-fields">
          <label>Exam date<input type="date" [min]="store.examSession().start" [max]="store.examSession().end" [value]="course.examDate" (change)="edit(course.courseId,{examDate:$any($event.target).value})"></label>
          <label>Priority<select [value]="course.priority" (change)="edit(course.courseId,{priority:+$any($event.target).value})">@for(option of priorities;track option.value){<option [value]="option.value">{{option.label}}</option>}</select></label>
          <label>Difficulty<select [value]="course.difficulty" (change)="edit(course.courseId,{difficulty:+$any($event.target).value})">@for(option of difficulties;track option.value){<option [value]="option.value">{{option.label}}</option>}</select></label>
          <label>Cap on hours<input type="number" min="0" max="5000" step="1" placeholder="no cap" [value]="course.maxStudyHours ?? ''" (change)="edit(course.courseId,{maxStudyHours:number($any($event.target).value)})"></label>
        </div>
      </div>
    }</div>

    <h3 class="setup-heading">Your day</h3>
    <div class="form-grid">
      <label>Day starts<input type="time" [value]="habits().dayStart" (change)="setHabit({dayStart:$any($event.target).value})"></label>
      <label>Day ends<input type="time" [value]="habits().dayEnd" (change)="setHabit({dayEnd:$any($event.target).value})"></label>
      <label>Lunch<input type="time" [value]="habits().lunch[0]" (change)="setMeal('lunch',0,$any($event.target).value)"></label>
      <label>until<input type="time" [value]="habits().lunch[1]" (change)="setMeal('lunch',1,$any($event.target).value)"></label>
      <label>Dinner<input type="time" [value]="habits().dinner[0]" (change)="setMeal('dinner',0,$any($event.target).value)"></label>
      <label>until<input type="time" [value]="habits().dinner[1]" (change)="setMeal('dinner',1,$any($event.target).value)"></label>
      <label>Study block (minutes)<input type="number" min="15" max="240" step="5" [value]="habits().studyBlockSize" (change)="setHabit({studyBlockSize:+$any($event.target).value})"></label>
      <label>Hours a week<input type="number" min="0" max="168" step="1" [value]="habits().studyHoursPerWeek ?? ''" (change)="setHabit({studyHoursPerWeek:number($any($event.target).value)})"></label>
    </div>
    <p class="field-hint">These times leave {{freeHours()}} h of free slots a week. The plan uses the hours above instead, spread over the days before each exam; raise it to {{freeHours()}} to fill every slot.</p>

    <h3 class="setup-heading">Days off</h3>
    <div class="setup-days-off">@for(day of habits().daysOff;track $index){
      <div class="setup-day-off">
        <label class="sr-only" [attr.for]="'day-off-'+$index">First day off</label>
        <input [id]="'day-off-'+$index" type="date" [min]="store.examSession().start" [max]="store.examSession().end" [value]="day.startDate" (change)="setDayOff($index,{startDate:$any($event.target).value})">
        <label>for<input type="number" min="1" max="400" step="1" [value]="day.rangeLength" (change)="setDayOff($index,{rangeLength:+$any($event.target).value})"> day(s)</label>
        <button type="button" class="icon-button" [attr.aria-label]="'Remove the days off from '+day.startDate" (click)="removeDayOff($index)"><app-icon name="trash" /></button>
      </div>
    }@empty{<p class="field-hint">No days off. Add the days you will not study at all.</p>}</div>
    <button type="button" class="text-button" (click)="addDayOff()"><app-icon name="plus" /> Add days off</button>

    @if(error()){<p class="form-error" role="alert">{{error()}}</p>}
    <div class="dialog-actions">
      <button type="button" class="text-button" (click)="dialog.close()">Cancel</button>
      <button type="button" class="button secondary" [disabled]="saving()" (click)="save(false)">Save</button>
      <button type="button" class="button primary" [disabled]="saving()||!courses().length" (click)="save(true)">
        @if(saving()){Saving…}@else{Save and generate}</button>
    </div>
  </dialog>
`})
export class ScheduleSetupComponent {
  readonly store=inject(StudyStore);
  readonly dialog=viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  readonly priorities=PRIORITIES;readonly difficulties=DIFFICULTIES;
  readonly habits=signal<Preferences>(this.store.preferences());
  readonly courses=signal<CourseDraft[]>([]);
  readonly saving=signal(false);readonly error=signal('');
  /** Study hours a full week offers at the chosen times, so the budget field has a yardstick. */
  readonly freeHours=computed(()=>{
    const h=this.habits();const span=(a:string,b:string)=>Math.max(0,this.minutes(b)-this.minutes(a));
    const day=span(h.dayStart,h.dayEnd)-span(h.lunch[0],h.lunch[1])-span(h.dinner[0],h.dinner[1]);
    return Math.round(Math.max(0,day)/60*7*10)/10;
  });
  /** What was on the server when the form opened, so only real changes are sent. */
  private original:CourseDraft[]=[];

  open():void{
    this.error.set('');
    this.habits.set(structuredClone(this.store.preferences()));
    this.original=this.store.planSubjects().filter(s=>!s.completed).map(s=>({
      courseId:s.courseId,name:s.name,color:s.color,examDate:s.examDate,
      priority:s.priority,difficulty:s.difficulty,maxStudyHours:s.maxStudyHours}));
    this.courses.set(this.original.map(course=>({...course})));
    this.dialog().nativeElement.showModal();
  }
  number(value:string):number|null{const trimmed=value.trim();return trimmed?Number(trimmed):null;}
  minutes(time:string):number{return Number(time.slice(0,2))*60+Number(time.slice(3));}
  edit(courseId:number,patch:Partial<CourseDraft>):void{this.courses.update(list=>list.map(c=>c.courseId===courseId?{...c,...patch}:c));}
  setHabit(patch:Partial<Preferences>):void{this.habits.update(h=>({...h,...patch}));}
  setMeal(meal:'lunch'|'dinner',index:0|1,value:string):void{
    this.habits.update(h=>{const pair=[...h[meal]] as [string,string];pair[index]=value;return {...h,[meal]:pair};});
  }
  addDayOff():void{this.habits.update(h=>({...h,daysOff:[...h.daysOff,{startDate:this.store.examSession().start,rangeLength:1}]}));}
  setDayOff(index:number,patch:Partial<DayOff>):void{
    this.habits.update(h=>({...h,daysOff:h.daysOff.map((day,i)=>i===index?{...day,...patch}:day)}));
  }
  removeDayOff(index:number):void{this.habits.update(h=>({...h,daysOff:h.daysOff.filter((_,i)=>i!==index)}));}

  /** Send the habits, then only the courses that changed, then optionally plan. */
  async save(thenGenerate:boolean):Promise<void>{
    this.saving.set(true);this.error.set('');
    try{
      if(!await this.store.savePreferences(this.habits())){this.error.set(this.store.planError());return;}
      for(const course of this.courses()){
        const before=this.original.find(c=>c.courseId===course.courseId);
        if(!before||(before.examDate===course.examDate&&before.priority===course.priority
          &&before.difficulty===course.difficulty&&before.maxStudyHours===course.maxStudyHours))continue;
        if(!await this.store.updateCoursePlan(course.courseId,{examDate:course.examDate,priority:course.priority,
          difficulty:course.difficulty,maxStudyHours:course.maxStudyHours})){this.error.set(this.store.planError());return;}
      }
      if(thenGenerate&&!await this.store.generate()){this.error.set(this.store.planError());return;}
      this.dialog().nativeElement.close();
    }finally{this.saving.set(false);}
  }
}
