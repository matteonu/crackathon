import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { ScheduleComponent } from '../components/schedule.component';
import { NextComponent } from '../components/next.component';
import { AnalyticsComponent } from '../components/analytics.component';
import { IconComponent } from '../shared/icon.component';

@Component({standalone:true,imports:[RouterLink,ScheduleComponent,NextComponent,AnalyticsComponent,IconComponent],template:`
  <header class="page-heading"><div><div class="breadcrumb">YOUR WORKSPACE <span>/</span> {{store.data().semester}}</div><h1>A clearer view of your study phase<span>.</span></h1><p>Your schedule, your next steps, your progress. All in one place.</p></div></header>
  <div class="page-stack"><app-schedule /><app-next /><div class="overview-bottom"><app-analytics /><aside class="modify-card"><span class="outline-icon"><app-icon name="settings" /></span><div><span class="eyebrow">MAKE ROOM FOR CHANGE</span><h2>Your plan.<br>Your pace.</h2><p>Adjust your hours and keep your study phase in balance.</p></div><a class="button secondary" routerLink="/schedule">Modify schedule <app-icon name="arrow" /></a></aside></div></div>
`})
export class OverviewComponent {readonly store=inject(StudyStore);}

