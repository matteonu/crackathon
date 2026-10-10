import { Routes } from '@angular/router';
import { OverviewComponent } from './pages/overview.component';
import { StudyComponent } from './pages/study.component';
import { AnalyticsPageComponent } from './pages/analytics-page.component';
import { SubjectComponent } from './pages/subject.component';

export const routes:Routes = [
  {path:'pdf/:id',loadComponent:()=>import('./pages/pdf-source.component').then(m=>m.PdfSourceComponent),title:'Source PDF · Studyphase'},
  {path:'',component:OverviewComponent,title:'Overview · Studyphase'},
  {path:'schedule',component:StudyComponent,title:'Schedule · Studyphase'},
  {path:'study-view',redirectTo:'schedule',pathMatch:'full'},
  {path:'analytics',component:AnalyticsPageComponent,title:'Analytics · Studyphase'},
  {path:'subject-tab/:id',component:SubjectComponent,title:'Subject · Studyphase'},
  {path:'**',redirectTo:''}
];
