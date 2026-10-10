import { Component, ElementRef, HostListener, afterNextRender, computed, inject, input, viewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { dayLabel } from '../models/study';
import { IconComponent } from '../shared/icon.component';
import { ScrollButtonsComponent } from '../shared/scroll-buttons.component';

@Component({selector:'app-schedule',standalone:true,imports:[RouterLink,IconComponent,ScrollButtonsComponent],templateUrl:'./schedule.component.html'})
export class ScheduleComponent {
  readonly store=inject(StudyStore);private readonly router=inject(Router);
  readonly expanded=input(false);
  readonly viewport=viewChild<ElementRef<HTMLDivElement>>('scheduleViewport');
  readonly visibleDates=computed(()=>this.expanded()?this.store.week():this.store.dates());
  readonly dateLabel=dayLabel;
  readonly weekday=(date:string)=>dayLabel(date,{weekday:'short'});
  readonly phaseLabel=computed(()=>`${dayLabel(this.store.dates()[0],{day:'numeric',month:'short',year:'numeric'})} – ${dayLabel(this.store.dates().at(-1)!,{day:'numeric',month:'short',year:'numeric'})} · recorded hours`);
  readonly weekLabel=computed(()=>`${dayLabel(this.store.week()[0])} – ${dayLabel(this.store.week()[6],{day:'numeric',month:'short',year:'numeric'})}`);
  readonly weekSubjects=computed(()=>this.store.subjects().filter(s=>this.store.hours(s,this.store.week())>0));
  constructor(){afterNextRender(()=>{if(!this.expanded()) {
    const index=this.store.dates().indexOf(this.store.week().find(d=>this.store.dates().includes(d))!);
    this.viewport()?.nativeElement.scrollTo({left:Math.max(0,index)*66});
  }});}
  @HostListener('document:keydown.escape') escape():void {if(this.expanded()&&!this.store.editor())void this.router.navigate(['/']);}
}
