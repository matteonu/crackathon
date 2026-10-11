import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { dayLabel } from '../models/study';
import { IconComponent } from '../shared/icon.component';

@Component({selector:'app-next',standalone:true,imports:[RouterLink,IconComponent],template:`
  <section class="panel next-panel" aria-labelledby="next-title">
    <div class="panel-heading"><div><h2 id="next-title">What’s next?</h2><p>Your subjects, next actions, and exam dates.</p></div></div>
    <div class="horizontal-scroll" tabindex="0" role="region" aria-label="Exam table, scroll horizontally">
      <table class="next-table"><caption class="sr-only">Exam sequence and next actions</caption><thead><tr><th scope="col">Subject</th><th scope="col">Next action</th><th scope="col">Exam date</th><th scope="col">Status</th></tr></thead>
      <tbody>@for(s of store.exams();track s.id){<tr><th scope="row"><a [routerLink]="['/subject-tab',s.id]"><span class="subject-dot" [style.background]="s.color"></span>{{s.name}}</a></th><td class="action-cell">{{s.nextAction || 'No next action set'}}</td><td class="nowrap">{{dateLabel(s.examDate)}}</td><td><button class="status-toggle" [class.is-done]="s.completed" [attr.aria-pressed]="s.completed" [attr.aria-label]="s.name+': '+(s.completed?'completed, mark as pending':'pending, mark as completed')" (click)="store.toggleDone(s.id)"><app-icon [name]="s.completed?'check':'clock'" />{{s.completed?'Done':'Pending'}}</button></td></tr>}@empty{<tr><td colspan="4" class="empty-state">No courses yet. Add your courses with + next to Your subjects in the sidebar.</td></tr>}</tbody></table>
    </div>
  </section>
`})
export class NextComponent {
  readonly store=inject(StudyStore);
  readonly dateLabel=(date:string)=>dayLabel(date,{day:'numeric',month:'short',year:'numeric'});
}
