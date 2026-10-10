import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { StudyStore } from '../services/study-store';
import { PlannedSession, dayLabel, round } from '../models/study';
import { PlanBlock, blockLabel, blockMinutes, minutesOf, studyHours } from '../models/semester';
import { IconComponent } from '../shared/icon.component';
import { ScheduleSetupComponent } from './schedule-setup.component';

@Component({selector:'app-calendar',standalone:true,imports:[ReactiveFormsModule,IconComponent,ScheduleSetupComponent],templateUrl:'./calendar.component.html'})
export class CalendarComponent {
  readonly store=inject(StudyStore);
  readonly sessionDialog=viewChild<ElementRef<HTMLDialogElement>>('sessionDialog');readonly proposalDialog=viewChild<ElementRef<HTMLDialogElement>>('proposalDialog');
  readonly setup=viewChild.required<ScheduleSetupComponent>('setup');
  readonly editingId=signal<string|null>(null);readonly error=signal('');readonly proposalError=signal('');
  /** The proposal being previewed: a whole plan, of which the shown week is a part. */
  readonly draft=signal<PlanBlock[]>([]);
  readonly form=new FormGroup({subjectId:new FormControl('',{nonNullable:true}),date:new FormControl('',{nonNullable:true}),start:new FormControl('09:00',{nonNullable:true}),hours:new FormControl<number|null>(2)});
  readonly weekLabel=computed(()=>`${dayLabel(this.store.week()[0])} – ${dayLabel(this.store.week()[6],{day:'numeric',month:'short',year:'numeric'})}`);
  readonly sessions=computed(()=>this.store.sessions().filter(s=>this.store.week().includes(s.date)).sort((a,b)=>a.start.localeCompare(b.start)));
  /** Blocks of the stored plan that fall in the shown week. */
  readonly planned=computed(()=>this.store.week().flatMap(date=>this.store.planOn(date)));
  readonly total=computed(()=>round(this.sessions().reduce((sum,s)=>sum+s.hours,0)));
  readonly plannedHours=computed(()=>studyHours(this.planned()));
  readonly firstHour=computed(()=>Math.min(8,...this.sessions().map(s=>Math.floor(this.start(s))),...this.planned().map(b=>Math.floor(minutesOf(b.start)/60))));
  readonly lastHour=computed(()=>Math.max(18,...this.sessions().map(s=>Math.ceil(this.start(s)+s.hours)),...this.planned().map(b=>Math.ceil(minutesOf(b.end)/60))));
  readonly ticks=computed(()=>Array.from({length:this.lastHour()-this.firstHour()},(_,i)=>this.firstHour()+i));
  readonly height=computed(()=>(this.lastHour()-this.firstHour())*56);
  /** The preview, limited to the week on screen so the list stays readable. */
  readonly draftWeek=computed(()=>this.draft().filter(b=>this.store.week().includes(b.date)&&b.type!=='meal'));
  readonly draftHours=computed(()=>studyHours(this.draft()));
  readonly draftDays=computed(()=>new Set(this.draft().filter(b=>b.type!=='meal').map(b=>b.date)).size);
  readonly draftTotals=computed(()=>this.store.subjects().map(subject=>({subject,
    hours:studyHours(this.draft().filter(b=>b.subjectId===subject.id))})).filter(entry=>entry.hours>0));
  readonly dayLabel=dayLabel;readonly weekday=(date:string)=>dayLabel(date,{weekday:'short'});
  readonly blockLabel=blockLabel;
  subject(id:string){return this.store.subjects().find(s=>s.id===id)!;}
  onDay(date:string):PlannedSession[]{return this.sessions().filter(s=>s.date===date);}
  blocksOn(date:string):PlanBlock[]{return this.store.planOn(date);}
  allowed(date:string):boolean{return this.store.dates().includes(date)&&date>=this.store.examSession().start&&date<=this.store.examSession().end;}
  hoursFor(id:string):number{return round(this.sessions().filter(s=>s.subjectId===id).reduce((sum,s)=>sum+s.hours,0));}
  start(s:PlannedSession):number{return Number(s.start.slice(0,2))+Number(s.start.slice(3))/60;}
  end(s:PlannedSession):string{const minutes=Math.round((this.start(s)+s.hours)*60);return `${String(Math.floor(minutes/60)).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;}
  top(block:PlanBlock):number{return (minutesOf(block.start)/60-this.firstHour())*56;}
  tall(block:PlanBlock):number{return Math.max(12,blockMinutes(block)/60*56-2);}
  color(block:PlanBlock):string{return block.subjectId?this.subject(block.subjectId)?.color??'#8A94A6':'#8A94A6';}
  name(block:PlanBlock):string{return block.subjectId?this.subject(block.subjectId)?.shortName??'Course':block.label??'Break';}
  open(date?:string,session?:PlannedSession):void{
    if(!this.store.subjects().length){this.store.announce('Add a course first, with + next to Your subjects.');return;}
    this.editingId.set(session?.id??null);this.error.set('');
    this.form.reset({subjectId:session?.subjectId??this.store.subjects()[0].id,date:session?.date??date??this.store.week().find(d=>this.allowed(d))??'',start:session?.start??'09:00',hours:session?.hours??2});
    this.sessionDialog()?.nativeElement.showModal();
  }
  save():void{
    try{const value=this.form.getRawValue();if(value.hours===null)throw new Error('Enter a duration.');const session:PlannedSession={...value,hours:value.hours,id:this.editingId()??crypto.randomUUID()};
      this.store.saveSessions([...this.store.sessions().filter(s=>s.id!==this.editingId()),session]);this.sessionDialog()?.nativeElement.close();
    }catch(e){this.error.set((e as Error).message);}
  }
  remove():void{this.store.saveSessions(this.store.sessions().filter(s=>s.id!==this.editingId()));this.sessionDialog()?.nativeElement.close();}
  openSetup():void{this.proposalDialog()?.nativeElement.close();this.setup().open();}
  /** Preview a proposal without storing it, so the user sees it before it lands. */
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
  /** Store the proposal. It replaces the plan from today on; past weeks stay. */
  async apply():Promise<void>{
    this.proposalError.set('');
    if(await this.store.generate()){this.draft.set([]);this.proposalDialog()?.nativeElement.close();}
    else this.proposalError.set(this.store.planError());
  }
}
