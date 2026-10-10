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
  readonly weekSubjects=computed(()=>this.store.subjects().filter(s=>this.store.hours(s,this.store.week())>0||this.store.planHoursFor(s.id,this.store.week())>0));
  readonly plannedWeek=computed(()=>Math.round(this.store.week().reduce((sum,date)=>sum+this.store.plannedDaily(date),0)*100)/100);
  /** A cell's fill: the subject's colour, deeper the more hours it holds. Recorded hours are
   *  strong; hours only planned are a light wash of the same colour, so the plan shows before
   *  anything is recorded. Mixed with white, so the fill is solid. */
  cellColor(subject:{id:string;color:string;hours:Record<string,number|null>},date:string):string|null{
    const recorded=subject.hours[date];const share=(h:number)=>Math.min(h,8)/8;
    if(recorded!=null)return `color-mix(in srgb, ${subject.color} ${Math.round(16+share(recorded)*44)}%, #fff)`;
    const plan=this.planned(subject.id,date);
    return plan?`color-mix(in srgb, ${subject.color} ${Math.round(6+share(plan)*16)}%, #fff)`:null;
  }
  /** Hours the plan asks of a subject on a day, 0 when it asks for none. */
  planned(subjectId:string,date:string):number{return this.store.planHoursFor(subjectId,[date]);}
  cellLabel(subject:{name:string;id:string;hours:Record<string,number|null>},date:string):string{
    const recorded=subject.hours[date];const plan=this.planned(subject.id,date);
    return `${subject.name}, ${dayLabel(date)}: ${recorded!=null?recorded+' hours recorded':plan?plan+' hours planned, none recorded':'unrecorded'}. Edit.`;
  }
  constructor(){afterNextRender(()=>{if(!this.expanded()) {
    const index=this.store.dates().indexOf(this.store.week().find(d=>this.store.dates().includes(d))!);
    this.viewport()?.nativeElement.scrollTo({left:Math.max(0,index)*66});
  }});}
  @HostListener('document:keydown.escape') escape():void {if(this.expanded()&&!this.store.editor())void this.router.navigate(['/']);}
}
