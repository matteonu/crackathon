import { Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { dayLabel } from '../models/study';
import { PlanBlock, blockLabel, dayHourDifferences, isStudyDayOff, mealBlock, minutesOf, studyHours, timeOf } from '../models/semester';
import type { HourDifference } from '../models/semester';
import { IconComponent } from '../shared/icon.component';
import { ScheduleSetupComponent } from './schedule-setup.component';

const HOUR=56;const SNAP=15;const MIN_SLOT=15;const BLOCK_GAP=6;
/** A gesture in progress: moving a slot, dragging one of its edges, or drawing a new one. */
interface Drag{mode:'move'|'start'|'end'|'create';id:number|null;date:string;start:number;end:number;
  originY:number;originDate:string;grab:number;moved:boolean;}
interface CalendarSlot extends PlanBlock{displayName:string;color:string;duration:number;top:number;height:number;
  isMeal:boolean;ariaLabel:string;title:string;deleteLabel:string;}

@Component({selector:'app-calendar',standalone:true,imports:[IconComponent,ScheduleSetupComponent],templateUrl:'./calendar.component.html'})
export class CalendarComponent {
  readonly store=inject(StudyStore);private readonly router=inject(Router);
  private readonly destroyRef=inject(DestroyRef);
  private gestureListeners:AbortController|null=null;
  private moveFrame:number|null=null;
  private pendingMove:PointerEvent|null=null;
  constructor(){this.destroyRef.onDestroy(()=>this.stopGestureListeners());}
  readonly chooser=viewChild<ElementRef<HTMLDialogElement>>('chooser');
  readonly setup=viewChild.required<ScheduleSetupComponent>('setup');
  readonly drag=signal<Drag|null>(null);
  /** The slot drawn on empty space, waiting for a course or a break to be chosen. */
  readonly pending=signal<{date:string;start:number;end:number}|null>(null);
  readonly weekLabel=computed(()=>`${dayLabel(this.store.week()[0])} – ${dayLabel(this.store.week()[6],{day:'numeric',month:'short',year:'numeric'})}`);
  private readonly blocksByDate=computed(()=>{
    const result=new Map<string,PlanBlock[]>();
    for(const block of this.store.generatedPlan()?.blocks??[]){
      const day=result.get(block.date);if(day)day.push(block);else result.set(block.date,[block]);
    }
    return result;
  });
  private readonly subjectsById=computed(()=>new Map(this.store.subjects().map(subject=>[subject.id,subject])));
  private readonly allowedDates=computed(()=>{
    const session=this.store.examSession();
    return new Set(this.store.dates().filter(date=>date>=session.start&&date<=session.end));
  });
  readonly dayLabels=computed(()=>new Map(this.store.week().map(date=>[date,{
    weekday:dayLabel(date,{weekday:'short'}),short:dayLabel(date),
    long:dayLabel(date,{weekday:'long',day:'numeric',month:'long'})
  }])));
  readonly planned=computed(()=>this.store.week().flatMap(date=>this.blocksByDate().get(date)??[]));
  readonly plannedHours=computed(()=>studyHours(this.planned()));
  private readonly subjectHours=computed(()=>{
    const grouped=new Map<string,PlanBlock[]>();
    for(const block of this.planned())if(block.subjectId){
      const slots=grouped.get(block.subjectId);if(slots)slots.push(block);else grouped.set(block.subjectId,[block]);
    }
    return new Map([...grouped].map(([id,blocks])=>[id,studyHours(blocks)]));
  });
  readonly daysOff=computed(()=>new Set(this.store.week().filter(date=>isStudyDayOff(date,this.store.preferences(),this.store.subjects()))));
  readonly timedExams=computed(()=>this.store.subjects().flatMap(subject=>
    this.store.week().includes(subject.examDate)&&subject.examStart&&subject.examEnd
      ? [{id:subject.id,name:subject.shortName,color:subject.color,date:subject.examDate,start:subject.examStart,end:subject.examEnd}]:[]));
  readonly hoursMismatches=computed(()=>{
    const result=new Map<string,HourDifference[]>();
    const subjects=this.store.subjects(), blocks=this.planned();
    for(const date of this.store.week()){
      const differences=dayHourDifferences(subjects,blocks,date);
      if(differences.length)result.set(date,differences);
    }
    return result;
  });
  /** The grid spans the user's day, and stretches for any slot outside it. */
  readonly firstHour=computed(()=>Math.min(Math.floor(minutesOf(this.store.preferences().dayStart)/60),...this.planned().map(b=>Math.floor(minutesOf(b.start)/60)),...this.timedExams().map(exam=>Math.floor(minutesOf(exam.start)/60))));
  readonly lastHour=computed(()=>Math.max(Math.ceil(minutesOf(this.store.preferences().dayEnd)/60),...this.planned().map(b=>Math.ceil(minutesOf(b.end)/60)),...this.timedExams().map(exam=>Math.ceil(minutesOf(exam.end)/60))));
  readonly ticks=computed(()=>Array.from({length:this.lastHour()-this.firstHour()},(_,i)=>this.firstHour()+i));
  readonly height=computed(()=>(this.lastHour()-this.firstHour())*HOUR);
  readonly dayLabel=dayLabel;
  readonly timeOf=timeOf;readonly minutesOf=minutesOf;
  private readonly slotsByDate=computed(()=>new Map(this.store.week().map(date=>[
    date,(this.blocksByDate().get(date)??[]).map(block=>this.slotView(block))
  ])));
  /** Only the dragged slot needs new display values while the pointer moves. */
  private readonly visibleSlots=computed(()=>{
    const base=this.slotsByDate(),d=this.drag();
    if(!d||d.mode==='create')return base;
    const block=(base.get(d.originDate)??[]).find(slot=>slot.id===d.id);if(!block)return base;
    const result=new Map(base);
    result.set(d.originDate,(base.get(d.originDate)??[]).filter(slot=>slot.id!==d.id));
    result.set(d.date,[...(result.get(d.date)??[]),this.slotView({...block,date:d.date,start:timeOf(d.start),end:timeOf(d.end)})]);
    return result;
  });
  private readonly examsByDate=computed(()=>new Map(this.store.week().map(date=>[
    date,this.timedExams().filter(exam=>exam.date===date)
  ])));
  private readonly mismatchLabels=computed(()=>new Map(this.store.week().map(date=>[
    date,this.buildHoursMismatchLabel(date)
  ])));
  /** Both generation actions compute the open week, cut to the study phase. */
  readonly planWeek=computed(()=>{const days=this.store.week().filter(d=>this.allowed(d));return days.length?{fromDate:days[0],toDate:days.at(-1)!}:null;});

  subject(id:string|null){return id?this.subjectsById().get(id):undefined;}
  allowed(date:string):boolean{return this.allowedDates().has(date);}
  /** A day's slots, with the one being dragged drawn where the pointer has it. */
  slotsOn(date:string):CalendarSlot[]{return this.visibleSlots().get(date)??[];}
  private slotView(block:PlanBlock):CalendarSlot{
    const subject=this.subject(block.subjectId),name=subject?.shortName??block.label??'Break';
    const start=minutesOf(block.start),end=minutesOf(block.end);
    return {...block,displayName:name,color:subject?.color??'#9aa39b',duration:end-start,
      top:this.top(start),height:this.tall(start,end),isMeal:mealBlock(block),
      ariaLabel:`${name}, ${blockLabel(block)}, ${this.dayLabels().get(block.date)?.short??dayLabel(block.date)}, ${block.start} to ${block.end}${block.subjectId?'. Open the subject.':''}`,
      title:`${name} · ${block.start}–${block.end}`,deleteLabel:`Delete ${name} at ${block.start}`};
  }
  ghost(date:string){const d=this.drag();return d?.mode==='create'&&d.date===date&&d.end>d.start?d:null;}
  top(minutes:number):number{return (minutes/60-this.firstHour())*HOUR;}
  /** Keep a visual gap between adjoining blocks without changing their clock times. */
  tall(start:number,end:number):number{return Math.max(8,(end-start)/60*HOUR-BLOCK_GAP);}
  hoursFor(id:string):number{return this.subjectHours().get(id)??0;}
  examsOn(date:string){return this.examsByDate().get(date)??[];}
  hoursMismatchLabel(date:string):string{return this.mismatchLabels().get(date)??'';}
  private buildHoursMismatchLabel(date:string):string{
    const details=(this.hoursMismatches().get(date)??[]).map(difference=>
      `${this.subject(difference.subjectId)?.shortName??difference.subjectId}: ${difference.plannedHours} h planned, ${difference.recordedHours===null?'no hours recorded':difference.recordedHours+' h recorded'}`);
    return `Hours differ from the calendar on ${dayLabel(date)}.\n${details.join('\n')}`;
  }

  // ---- pointer geometry
  private minutesAt(clientY:number,date:string):number{
    const day=document.querySelector<HTMLElement>(`.calendar-day[data-date="${date}"]`);if(!day)return 0;
    const raw=this.firstHour()*60+(clientY-day.getBoundingClientRect().top)/HOUR*60;
    return Math.max(this.firstHour()*60,Math.min(this.lastHour()*60,Math.round(raw/SNAP)*SNAP));
  }
  private dayAt(clientX:number,clientY:number):string|null{
    const el=document.elementsFromPoint(clientX,clientY).find(e=>e.classList.contains('calendar-day'));
    const date=el?.getAttribute('data-date')??null;return date&&this.allowed(date)?date:null;
  }

  // ---- gestures
  startCreate(event:PointerEvent,date:string):void{
    if(event.button!==0||event.target!==event.currentTarget||!this.allowed(date))return;
    if(!this.store.subjects().length){this.store.announce('Add a course first, with + next to Your subjects.');return;}
    const at=Math.floor(this.minutesAt(event.clientY,date)/SNAP)*SNAP;
    this.drag.set({mode:'create',id:null,date,start:at,end:at,originY:event.clientY,originDate:date,grab:at,moved:false});
    this.listenForGesture(event.pointerId);
    event.preventDefault();
  }
  startMove(event:PointerEvent,block:PlanBlock,mode:'move'|'start'|'end'):void{
    if(event.button!==0||block.id===null)return;
    event.stopPropagation();event.preventDefault();
    const start=minutesOf(block.start),end=minutesOf(block.end);
    this.drag.set({mode,id:block.id,date:block.date,start,end,originY:event.clientY,originDate:block.date,
      grab:this.minutesAt(event.clientY,block.date)-start,moved:false});
    this.listenForGesture(event.pointerId);
  }
  /** Native listeners exist only during a gesture; idle pointer movement never checks the calendar. */
  private listenForGesture(pointerId:number):void{
    this.stopGestureListeners();
    const controller=new AbortController();this.gestureListeners=controller;
    const options={signal:controller.signal};
    window.addEventListener('pointermove',event=>{
      if(event.pointerId!==pointerId)return;
      this.pendingMove=event;
      if(this.moveFrame===null)this.moveFrame=requestAnimationFrame(()=>this.flushPointerMove());
    },options);
    window.addEventListener('pointerup',event=>{
      if(event.pointerId!==pointerId)return;
      // Apply the last move even when release happens before the next animation frame.
      this.flushPointerMove();this.pointerUp();
    },options);
    window.addEventListener('pointercancel',event=>{if(event.pointerId===pointerId)this.cancelDrag();},options);
    window.addEventListener('keydown',event=>{if(event.key==='Escape')this.cancelDrag();},options);
    window.addEventListener('blur',()=>this.cancelDrag(),options);
  }
  private flushPointerMove():void{
    if(this.moveFrame!==null)cancelAnimationFrame(this.moveFrame);
    this.moveFrame=null;
    const event=this.pendingMove;this.pendingMove=null;
    if(event)this.pointerMove(event);
  }
  private stopGestureListeners():void{
    this.gestureListeners?.abort();this.gestureListeners=null;
    if(this.moveFrame!==null)cancelAnimationFrame(this.moveFrame);
    this.moveFrame=null;this.pendingMove=null;
  }
  pointerMove(event:PointerEvent):void{
    const d=this.drag();if(!d)return;
    const moved=d.moved||Math.abs(event.clientY-d.originY)>4;
    if(d.mode==='create'){
      // `grab` holds where the pointer went down; the slot stretches from there either way.
      const at=this.minutesAt(event.clientY,d.date);
      this.drag.set({...d,start:Math.min(d.grab,at),end:Math.max(d.grab,at),moved});return;
    }
    if(d.mode==='move'){
      const date=this.dayAt(event.clientX,event.clientY)??d.date;const length=d.end-d.start;
      let start=this.minutesAt(event.clientY,date)-d.grab;start=Math.round(start/SNAP)*SNAP;
      start=Math.max(this.firstHour()*60,Math.min(this.lastHour()*60-length,start));
      this.drag.set({...d,date,start,end:start+length,moved:moved||date!==d.originDate});return;
    }
    const at=this.minutesAt(event.clientY,d.date);
    this.drag.set(d.mode==='start'?{...d,start:Math.min(at,d.end-MIN_SLOT),moved}:{...d,end:Math.max(at,d.start+MIN_SLOT),moved});
  }
  pointerUp():void{
    this.stopGestureListeners();
    const d=this.drag();if(!d)return;this.drag.set(null);
    if(d.mode==='create'){
      // A plain click draws one study block of the usual length.
      const end=d.moved&&d.end-d.start>=MIN_SLOT?d.end:d.start+this.store.preferences().studyBlockSize;
      this.pending.set({date:d.date,start:d.start,end:Math.min(end,24*60-1)});this.chooser()?.nativeElement.showModal();return;
    }
    const block=this.store.generatedPlan()?.blocks.find(b=>b.id===d.id);if(!block)return;
    if(!d.moved){if(d.mode==='move'&&block.subjectId)void this.router.navigate(['/subject-tab',block.subjectId]);return;}
    const patch:{date?:string;start?:string;end?:string}={};
    if(d.date!==block.date)patch.date=d.date;if(timeOf(d.start)!==block.start)patch.start=timeOf(d.start);if(timeOf(d.end)!==block.end)patch.end=timeOf(d.end);
    if(Object.keys(patch).length)void this.store.moveSlot(d.id!,patch);
  }
  cancelDrag():void{this.stopGestureListeners();this.drag.set(null);}
  remove(block:PlanBlock):void{if(block.id!==null)void this.store.deleteSlot(block.id);}
  /** The day being planned by its + button, so that button can show it is busy. */
  readonly planningDay=signal<string|null>(null);
  hasSlots(date:string):boolean{return (this.blocksByDate().get(date)?.length??0)>0;}
  async planDay(date:string):Promise<void>{
    if(!this.store.subjects().length){this.store.announce('Add a course first, with + next to Your subjects.');return;}
    const week=this.planWeek();if(!week||!this.allowed(date))return;
    this.planningDay.set(date);
    try{if(await this.store.planDay(date,week))this.store.announce(`${dayLabel(date,{weekday:'long',day:'numeric',month:'short'})} is planned.`);}
    finally{this.planningDay.set(null);}
  }
  clearDay(date:string):void{void this.store.clearDay(date);}
  open(block:PlanBlock):void{if(block.subjectId)void this.router.navigate(['/subject-tab',block.subjectId]);}
  async choose(kind:'course'|'break',courseId?:number):Promise<void>{
    const p=this.pending();if(!p)return;this.chooser()?.nativeElement.close();this.pending.set(null);
    await this.store.createSlot({date:p.date,start:timeOf(p.start),end:timeOf(p.end),kind,...(courseId!==undefined?{courseId}:{})});
  }

  // ---- generation
  openSetup():void{this.setup().open();}
  async generateWeek():Promise<void>{
    if(!this.store.subjects().length){this.store.announce('Add a course first, with + next to Your subjects.');return;}
    const week=this.planWeek();
    if(!week){this.store.announce('This week is outside the study phase. Pick a week inside it.');return;}
    if(await this.store.generate(week))await this.store.load();
  }
}
