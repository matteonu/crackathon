import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { StudyStore } from '../services/study-store';
import { StudyDemoService } from '../services/study-demo.service';
import { PlannedSession, dayLabel, round } from '../models/study';
import { IconComponent } from '../shared/icon.component';

@Component({selector:'app-calendar',standalone:true,imports:[ReactiveFormsModule,IconComponent],templateUrl:'./calendar.component.html'})
export class CalendarComponent {
  readonly store=inject(StudyStore);private readonly demo=inject(StudyDemoService);
  readonly sessionDialog=viewChild<ElementRef<HTMLDialogElement>>('sessionDialog');readonly proposalDialog=viewChild<ElementRef<HTMLDialogElement>>('proposalDialog');
  readonly editingId=signal<string|null>(null);readonly error=signal('');readonly proposalError=signal('');readonly draft=signal<PlannedSession[]>([]);private variation=0;
  readonly form=new FormGroup({subjectId:new FormControl('',{nonNullable:true}),date:new FormControl('',{nonNullable:true}),start:new FormControl('09:00',{nonNullable:true}),hours:new FormControl<number|null>(2)});
  readonly weekLabel=computed(()=>`${dayLabel(this.store.week()[0])} – ${dayLabel(this.store.week()[6],{day:'numeric',month:'short',year:'numeric'})}`);
  readonly sessions=computed(()=>this.store.sessions().filter(s=>this.store.week().includes(s.date)).sort((a,b)=>a.start.localeCompare(b.start)));
  readonly total=computed(()=>round(this.sessions().reduce((sum,s)=>sum+s.hours,0)));
  readonly firstHour=computed(()=>Math.min(8,...this.sessions().map(s=>Math.floor(this.start(s)))));
  readonly lastHour=computed(()=>Math.max(18,...this.sessions().map(s=>Math.ceil(this.start(s)+s.hours))));
  readonly ticks=computed(()=>Array.from({length:this.lastHour()-this.firstHour()},(_,i)=>this.firstHour()+i));
  readonly height=computed(()=>(this.lastHour()-this.firstHour())*56);
  readonly draftHours=computed(()=>round(this.draft().reduce((sum,s)=>sum+s.hours,0)));
  readonly dayLabel=dayLabel;readonly weekday=(date:string)=>dayLabel(date,{weekday:'short'});
  subject(id:string){return this.store.subjects().find(s=>s.id===id)!;}
  onDay(date:string):PlannedSession[]{return this.sessions().filter(s=>s.date===date);}
  allowed(date:string):boolean{return this.store.dates().includes(date)&&date>=this.store.examSession().start&&date<=this.store.examSession().end;}
  hoursFor(id:string):number{return round(this.sessions().filter(s=>s.subjectId===id).reduce((sum,s)=>sum+s.hours,0));}
  start(s:PlannedSession):number{return Number(s.start.slice(0,2))+Number(s.start.slice(3))/60;}
  end(s:PlannedSession):string{const minutes=Math.round((this.start(s)+s.hours)*60);return `${String(Math.floor(minutes/60)).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;}
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
  propose():void{this.regenerate();this.proposalDialog()?.nativeElement.showModal();}
  regenerate():void{this.proposalError.set('');this.draft.set(this.demo.proposal(this.store.data(),this.store.week(),this.variation++));}
  apply():void{try{this.store.saveSessions([...this.store.sessions(),...this.draft()]);this.proposalDialog()?.nativeElement.close();}catch(e){this.proposalError.set((e as Error).message);}}
}
