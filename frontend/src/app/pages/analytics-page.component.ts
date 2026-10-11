import { Component } from '@angular/core';
import { AnalyticsComponent } from '../components/analytics.component';
@Component({standalone:true,imports:[AnalyticsComponent],template:`<app-analytics [detailed]="true" />`})
export class AnalyticsPageComponent {}
