import { Component } from '@angular/core';
import { AnalyticsComponent } from '../components/analytics.component';
@Component({standalone:true,imports:[AnalyticsComponent],template:`<header class="page-heading"><div><div class="breadcrumb">YOUR WORKSPACE <span>/</span> ANALYTICS</div><h1>See how far you’ve come<span>.</span></h1><p>Study time and flashcard progress across the whole semester.</p></div></header><app-analytics [detailed]="true" />`})
export class AnalyticsPageComponent {}
