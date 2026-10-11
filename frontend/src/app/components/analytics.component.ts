import { Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { IconComponent } from '../shared/icon.component';
import { RecallAnalyticsComponent } from './recall-analytics.component';
import { ScheduleStatsComponent } from './schedule-stats.component';
import { activityWeeks, type ActivityDay } from '../models/analytics';

@Component({selector:'app-analytics',standalone:true,imports:[RouterLink,IconComponent,RecallAnalyticsComponent,ScheduleStatsComponent],template:`
  <section class="panel analytics-panel" aria-labelledby="analytics-title"><div class="panel-heading"><div><h2 id="analytics-title">Analytics</h2><p>A little perspective on your progress.</p></div>@if(!detailed()){<a routerLink="/analytics" class="text-button" aria-label="More analytics"><span class="optional-text">More statistics</span><app-icon name="arrow" /></a>}</div>
    <div class="metric-row">
      <article class="metric-card total-metric"><span class="eyebrow" title="Target hours forecast the full study phase from your Schedule settings, study days, days off, exams and course caps. Recall is included.">RECORDED / TARGET</span><div class="goal-ring" role="meter" aria-label="Overall study goal" aria-valuemin="0" aria-valuemax="100" [attr.aria-valuenow]="cappedPercent()" [attr.aria-valuetext]="store.totalHours()+' hours recorded of '+store.targetHours()+' target hours'">
        <svg viewBox="0 0 120 120" aria-hidden="true"><circle class="goal-ring-track" cx="60" cy="60" r="51" /><circle class="goal-ring-fill" cx="60" cy="60" r="51" pathLength="100" [attr.stroke-dasharray]="cappedPercent()+' 100'" /></svg>
        <div class="goal-ring-value"><strong>{{store.totalHours()}}<span> h</span></strong><span>of {{store.targetHours()}} h</span><small>{{percent()}}%</small></div>
      </div><p>{{differenceLabel()}}</p></article>
      <article class="metric-card hours-metric"><span class="eyebrow">RECORDED HOURS</span><div class="mini-bars">@for(s of store.subjects();track s.id){<a [routerLink]="['/subject-tab',s.id]"><span class="metric-course-name" [title]="s.shortName">{{s.shortName}}</span><div class="bar-track"><i [style.background]="s.color" [style.width.%]="store.hours(s)/maxHours()*100"></i></div><strong>{{store.hours(s)}} h</strong></a>}</div></article>
      <article class="metric-card balance-metric"><span class="eyebrow">SUBJECT BALANCE</span><div class="balance-list">@for(s of store.subjects();track s.id){<div class="balance-row"><span><i class="subject-dot" [style.background]="s.color"></i><span class="metric-course-name" [title]="s.shortName">{{s.shortName}}</span></span><strong [class.amber-text]="store.remaining(s)>0">{{balance(s.id)}}</strong></div>}</div></article>
      <article class="metric-card activity-metric"><span class="eyebrow">DAILY STUDY ACTIVITY</span>
        <div class="activity-chart" [style.--activity-weeks]="activity().length || 1"><div class="activity-scroll" tabindex="0" role="region" aria-label="Daily study hours, calendar by week">
          <div class="activity-calendar"><div class="activity-weekday-labels" aria-hidden="true"><span></span><span>Mon</span><span></span><span>Wed</span><span></span><span>Fri</span><span></span><span></span></div>
            @for(week of activity();track week.start){<div class="activity-week"><span class="activity-month" aria-hidden="true">{{week.month}}</span>@for(day of week.days;track $index){@if(day){<span class="activity-tile" [attr.data-level]="day.level" tabindex="0" [attr.aria-label]="activityLabel(day)" [attr.title]="activityLabel(day)"></span>}@else{<span class="activity-tile activity-padding" aria-hidden="true"></span>}}</div>}
          </div>
        </div><div class="activity-legend" aria-label="Study hours: empty, under 2, 2 to 4, 4 to 6, and 6 or more hours"><span>0 h</span>@for(level of [0,1,2,3,4];track level){<i class="activity-tile" [attr.data-level]="level" aria-hidden="true"></i>}<span>6+ h</span></div></div>
        <p><strong>{{store.recordedDays()}}</strong> of {{store.dates().length}} days recorded</p><span class="muted">{{average()}} h per recorded day</span>
      </article>
    </div>
    <div class="panel-foot"><span>Across the complete study phase</span></div>
  </section>
  @if(detailed()){
    <app-schedule-stats />
    <app-recall-analytics />
  }
`})
export class AnalyticsComponent {
  readonly store=inject(StudyStore);readonly detailed=input(false);
  readonly percent=computed(()=>this.store.targetHours()?Math.round(this.store.totalHours()/this.store.targetHours()*1000)/10:0);
  readonly cappedPercent=computed(()=>Math.min(100,this.percent()));
  readonly maxHours=computed(()=>Math.max(1,...this.store.subjects().map(s=>this.store.hours(s))));
  readonly average=computed(()=>this.store.recordedDays()?Math.round(this.store.totalHours()/this.store.recordedDays()*10)/10:0);
  readonly activity=computed(()=>activityWeeks(this.store.data()));
  readonly differenceLabel=computed(()=>{const d=Math.round((this.store.totalHours()-this.store.targetHours())*100)/100;return `${Math.abs(d)} h ${d>=0?'above plan':'left overall'}`;});
  balance(id:string):string {const s=this.store.subjects().find(s=>s.id===id)!;const r=this.store.remaining(s);return r===0?'On target':`${Math.abs(r)} h ${r<0?'above':'left'}`;}
  activityLabel(day:ActivityDay):string {const date=new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(day.date+'T12:00:00Z'));return `${date}: ${day.recorded?day.hours+' h studied':'No hours recorded'}`;}
}
