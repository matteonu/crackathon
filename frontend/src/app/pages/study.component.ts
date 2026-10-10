import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ScheduleComponent } from '../components/schedule.component';
import { CalendarComponent } from '../components/calendar.component';
import { StudyStore } from '../services/study-store';
@Component({standalone:true,imports:[ScheduleComponent,CalendarComponent],template:`
  <header class="page-heading"><div><div class="breadcrumb">YOUR WORKSPACE <span>/</span> SCHEDULE</div><h1>Make time for what matters<span>.</span></h1><p>Plan your study sessions and keep track of the time you put in.</p></div><div class="view-toggle" role="group" aria-label="Schedule view"><button [class.active]="view()==='calendar'" [attr.aria-pressed]="view()==='calendar'" (click)="view.set('calendar')">Calendar</button><button [class.active]="view()==='hours'" [attr.aria-pressed]="view()==='hours'" (click)="view.set('hours')">Hours overview</button></div></header>
  @if(view()==='calendar'){<app-calendar />}@else{<app-schedule [expanded]="true" />}
`})
export class StudyComponent {
  readonly store=inject(StudyStore);
  /** ?view=hours opens the hours overview, which is where Full detail on the overview leads. */
  readonly view=signal<'calendar'|'hours'>(inject(ActivatedRoute).snapshot.queryParamMap.get('view')==='hours'?'hours':'calendar');
}
