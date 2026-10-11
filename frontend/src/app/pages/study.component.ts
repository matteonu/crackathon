import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ScheduleComponent } from '../components/schedule.component';
import { CalendarComponent } from '../components/calendar.component';
import { StudyStore } from '../services/study-store';
import { NgTemplateOutlet } from '@angular/common';
@Component({standalone:true,imports:[ScheduleComponent,CalendarComponent,NgTemplateOutlet],template:`
  <ng-template #viewSwitch><div class="learning-mode-options schedule-view-toggle" [class.deep-selected]="selection()==='hours'" role="group" aria-label="Schedule view"><button [class.selected]="selection()==='calendar'" [attr.aria-pressed]="selection()==='calendar'" (click)="selectView('calendar')">Calendar</button><button [class.selected]="selection()==='hours'" [attr.aria-pressed]="selection()==='hours'" (click)="selectView('hours')">Hours overview</button></div></ng-template>
  @if(view()==='calendar'){<app-calendar><div schedule-view-switch><ng-container [ngTemplateOutlet]="viewSwitch" /></div></app-calendar>}
  @else{<app-schedule [expanded]="true"><div schedule-view-switch><ng-container [ngTemplateOutlet]="viewSwitch" /></div></app-schedule>}
`})
export class StudyComponent {
  readonly store=inject(StudyStore);
  private initializedView='';
  constructor(){
    effect(()=>{
      const view=this.view();
      if(!this.store.loaded())return;
      const phase=this.store.examSession(),today=this.store.currentDate();
      const key=`${this.store.semkez()}:${view}:${phase.start}:${phase.end}`;
      // Initialize after the plan loads and when the view/phase changes. Saving
      // hours or browsing weeks must not snap the selection back to its default.
      if(this.initializedView===key)return;
      this.initializedView=key;
      const date=view==='hours'&&(today<phase.start||today>phase.end)?phase.start:today;
      untracked(()=>this.store.setWeek(date));
    });
    inject(DestroyRef).onDestroy(()=>clearTimeout(this.switchTimer));
  }
  /** ?view=hours opens the hours overview, which is where Full detail on the overview leads. */
  readonly view=signal<'calendar'|'hours'>(inject(ActivatedRoute).snapshot.queryParamMap.get('view')==='hours'?'hours':'calendar');
  readonly selection=signal(this.view());
  private switchTimer?:ReturnType<typeof setTimeout>;
  selectView(view:'calendar'|'hours'):void{
    clearTimeout(this.switchTimer);
    this.selection.set(view);
    // Let the shared sliding selector finish before replacing its containing panel.
    if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)this.view.set(view);
    else this.switchTimer=setTimeout(()=>this.view.set(view),220);
  }
}
