import { Component, ElementRef, HostListener, computed, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { dayLabel } from '../models/study';
import { PlanBlock, blockLabel, minutesOf, studyHours, timeOf } from '../models/semester';
import { IconComponent } from '../shared/icon.component';
import { ScheduleSetupComponent } from './schedule-setup.component';

const HOUR=56;const SNAP=15;const MIN_SLOT=15;
/** A gesture in progress: moving a slot, dragging one of its edges, or drawing a new one. */
interface Drag{mode:'move'|'start'|'end'|'create';id:number|null;date:string;start:number;end:number;
  originY:number;originDate:string;grab:number;moved:boolean;}

@Component({selector:'app-calendar',standalone:true,imports:[IconComponent,ScheduleSetupComponent],templateUrl:'./calendar.component.html'})
export class CalendarComponent {
  readonly store=inject(StudyStore);private readonly router=inject(Router);
  readonly proposalDialog=viewChild<ElementRef<HTMLDialogElement>>('proposalDialog');
  readonly chooser=viewChild<ElementRef<HTMLDialogElement>>('chooser');
  readonly setup=viewChild.required<ScheduleSetupComponent>('setup');
  readonly proposalError=signal('');readonly draft=signal<PlanBlock[]>([]);
  readonly drag=signal<Drag|null>(null);
  /** The slot drawn on empty space, waiting for a course or a break to be chosen. */
  readonly pending=signal<{date:string;start:number;end:number}|null>(null);
  readonly weekLabel=computed(()=>`${dayLabel(this.store.week()[0])} – ${dayLabel(this.store.week()[6],{day:'numeric',month:'short',year:'numeric'})}`);
  readonly planned=computed(()=>this.store.week().flatMap(date=>this.store.planOn(date)));
  readonly plannedHours=computed(()=>studyHours(this.planned()));
  /** The grid spans the user's day, and stretches for any slot outside it. */
  readonly firstHour=computed(()=>Math.min(Math.floor(minutesOf(this.store.preferences().dayStart)/60),...this.planned().map(b=>Math.floor(minutesOf(b.start)/60))));
  readonly lastHour=computed(()=>Math.max(Math.ceil(minutesOf(this.store.preferences().dayEnd)/60),...this.planned().map(b=>Math.ceil(minutesOf(b.end)/60))));
  readonly ticks=computed(()=>Array.from({length:this.lastHour()-this.firstHour()},(_,i)=>this.firstHour()+i));
  readonly height=computed(()=>(this.lastHour()-this.firstHour())*HOUR);
  readonly draftWeek=computed(()=>this.draft().filter(b=>this.store.week().includes(b.date)&&b.type!=='meal'));
  readonly draftHours=computed(()=>studyHours(this.draft()));
  readonly draftDays=computed(()=>new Set(this.draft().filter(b=>b.type!=='meal').map(b=>b.date)).size);
  readonly draftTotals=computed(()=>this.store.subjects().map(subject=>({subject,
    hours:studyHours(this.draft().filter(b=>b.subjectId===subject.id))})).filter(entry=>entry.hours>0));
  readonly dayLabel=dayLabel;readonly weekday=(date:string)=>dayLabel(date,{weekday:'short'});
  readonly blockLabel=blockLabel;readonly timeOf=timeOf;readonly minutesOf=minutesOf;

  subject(id:string|null){return id?this.store.subjects().find(s=>s.id===id):undefined;}
  allowed(date:string):boolean{return this.store.dates().includes(date)&&date>=this.store.examSession().start&&date<=this.store.examSession().end;}
  /** A day's slots, with the one being dragged drawn where the pointer has it. */
  slotsOn(date:string):PlanBlock[]{
    const d=this.drag();const blocks=this.store.planOn(date).filter(b=>!d||d.mode==='create'||b.id!==d.id);
    if(d&&d.mode!=='create'&&d.date===date){const b=this.store.generatedPlan()?.blocks.find(x=>x.id===d.id);if(b)blocks.push({...b,date,start:timeOf(d.start),end:timeOf(d.end)});}
    return blocks;
  }
  ghost(date:string){const d=this.drag();return d?.mode==='create'&&d.date===date&&d.end>d.start?d:null;}
  top(minutes:number):number{return (minutes/60-this.firstHour())*HOUR;}
  tall(start:number,end:number):number{return Math.max(14,(end-start)/60*HOUR-2);}
  color(block:PlanBlock):string{return this.subject(block.subjectId)?.color??'#9aa39b';}
  name(block:PlanBlock):string{return this.subject(block.subjectId)?.shortName??block.label??'Break';}
  hoursFor(id:string):number{return this.store.planHoursFor(id,this.store.week());}

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
    event.preventDefault();
  }
  startMove(event:PointerEvent,block:PlanBlock,mode:'move'|'start'|'end'):void{
    if(event.button!==0||block.id===null)return;
    event.stopPropagation();event.preventDefault();
    const start=minutesOf(block.start),end=minutesOf(block.end);
    this.drag.set({mode,id:block.id,date:block.date,start,end,originY:event.clientY,originDate:block.date,
      grab:this.minutesAt(event.clientY,block.date)-start,moved:false});
  }
  @HostListener('window:pointermove',['$event']) pointerMove(event:PointerEvent):void{
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
  @HostListener('window:pointerup') pointerUp():void{
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
  @HostListener('window:keydown.escape') cancelDrag():void{this.drag.set(null);}
  remove(block:PlanBlock):void{if(block.id!==null)void this.store.deleteSlot(block.id);}
  open(block:PlanBlock):void{if(block.subjectId)void this.router.navigate(['/subject-tab',block.subjectId]);}
  async choose(kind:'course'|'break',courseId?:number):Promise<void>{
    const p=this.pending();if(!p)return;this.chooser()?.nativeElement.close();this.pending.set(null);
    await this.store.createSlot({date:p.date,start:timeOf(p.start),end:timeOf(p.end),kind,...(courseId!==undefined?{courseId}:{})});
  }

  // ---- proposal
  openSetup():void{this.proposalDialog()?.nativeElement.close();this.setup().open();}
  async propose():Promise<void>{
    if(!this.store.subjects().length){this.store.announce('Add a course first, with + next to Your subjects.');return;}
    await this.regenerate();
    if(this.draft().length||this.proposalError())this.proposalDialog()?.nativeElement.showModal();
  }
  async regenerate():Promise<void>{
    this.proposalError.set('');
    const plan=await this.store.generate({dryRun:true});
    this.draft.set(plan?.blocks??[]);
    if(!plan)this.proposalError.set(this.store.planError());
  }
  async apply():Promise<void>{
    this.proposalError.set('');
    if(await this.store.generate()){this.draft.set([]);this.proposalDialog()?.nativeElement.close();await this.store.load();}
    else this.proposalError.set(this.store.planError());
  }
}
