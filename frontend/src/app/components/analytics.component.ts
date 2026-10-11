import { Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { IconComponent } from '../shared/icon.component';
import { RecallAnalyticsComponent } from './recall-analytics.component';
import { ScheduleStatsComponent } from './schedule-stats.component';

@Component({selector:'app-analytics',standalone:true,imports:[RouterLink,IconComponent,RecallAnalyticsComponent,ScheduleStatsComponent],template:`
  <section class="panel analytics-panel" aria-labelledby="analytics-title"><div class="panel-heading"><div><h2 id="analytics-title">Analytics</h2><p>A little perspective on your progress.</p></div>@if(!detailed()){<a routerLink="/analytics" class="text-button" aria-label="More analytics"><span class="optional-text">More statistics</span><app-icon name="arrow" /></a>}</div>
    <div class="horizontal-scroll analytics-scroll" tabindex="0" role="region" aria-label="Analytics cards, scroll horizontally"><div class="metric-row">
      <article class="metric-card total-metric"><span class="eyebrow" title="Target hours forecast the full study phase from your Schedule settings, study days, days off, exams and course caps. Recall is included.">RECORDED / TARGET</span><div class="hero-metric">{{store.totalHours()}}<span>h</span><small>/ {{store.targetHours()}} h</small></div><div class="progress-track" role="meter" aria-label="Overall study goal" aria-valuemin="0" aria-valuemax="100" [attr.aria-valuenow]="cappedPercent()"><span [style.width.%]="cappedPercent()"></span></div><p>{{percent()}}% of target <span class="muted">· {{differenceLabel()}}</span></p></article>
      <article class="metric-card hours-metric"><span class="eyebrow">RECORDED HOURS</span><div class="mini-bars">@for(s of store.subjects();track s.id){<a [routerLink]="['/subject-tab',s.id]"><span>{{s.shortName}}</span><div class="bar-track"><i [style.background]="s.color" [style.width.%]="store.hours(s)/maxHours()*100"></i></div><strong>{{store.hours(s)}} h</strong></a>}</div></article>
      <article class="metric-card balance-metric"><span class="eyebrow">SUBJECT BALANCE</span>@for(s of store.subjects();track s.id){<div class="balance-row"><span><i class="subject-dot" [style.background]="s.color"></i>{{s.shortName}}</span><strong [class.amber-text]="store.remaining(s)>0">{{balance(s.id)}}</strong></div>}</article>
      <article class="metric-card"><span class="eyebrow">DAYS WITH A RECORD</span><div class="hero-metric">{{store.recordedDays()}}<small>/ {{store.dates().length}}</small></div><p>{{average()}} h per recorded day</p><span class="muted">Blank cells stay unrecorded.</span></article>
    </div></div>
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
  readonly differenceLabel=computed(()=>{const d=Math.round((this.store.totalHours()-this.store.targetHours())*100)/100;return `${Math.abs(d)} h ${d>=0?'above plan':'left overall'}`;});
  balance(id:string):string {const s=this.store.subjects().find(s=>s.id===id)!;const r=this.store.remaining(s);return r===0?'On target':`${Math.abs(r)} h ${r<0?'above':'left'}`;}
}
