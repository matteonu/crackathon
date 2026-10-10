import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { StudyStore } from '../services/study-store';
import { MaterialStore } from '../services/material-store';
import { SchedulerService } from '../services/scheduler.service';
import { recallSnapshot } from '../models/recall';
import { PlanVsRecordedDay, SubjectStat, asOfDate, recentPlanVsRecorded, round1, subjectStats } from '../models/analytics';
import { IconComponent } from '../shared/icon.component';
import { MaterialLibraryComponent } from '../components/material-library.component';
import { TaskListComponent } from '../components/task-list.component';

@Component({standalone:true,imports:[RouterLink,FormsModule,IconComponent,MaterialLibraryComponent,TaskListComponent],template:`
  @if(subject();as s){
    <header class="page-heading"><div><div class="breadcrumb">YOUR WORKSPACE <span>/</span> SUBJECTS</div><h1><span class="subject-dot heading-dot" [style.background]="s.color"></span>{{s.name}}<span>.</span></h1>
      <div class="subject-meta"><span>{{s.lectureId || 'Lecture ID not set'}}</span><span>{{s.ects===undefined?'ECTS not set':s.ects+' ECTS'}}</span>@if(s.homepage){<a [href]="s.homepage" target="_blank" rel="noopener noreferrer">Course catalogue ↗</a>}</div>
    </div><div class="heading-actions"><button class="icon-button" aria-label="Subject details" title="Subject details" aria-haspopup="dialog" (click)="openDetails(detailsDialog)"><app-icon name="settings" /></button><button class="button primary" (click)="store.openEditor(s.id)"><app-icon name="plus" /> Record hours</button></div></header>
    <section class="panel subject-progress" aria-labelledby="progress-title"><div class="panel-heading"><h2 id="progress-title">Your progress</h2></div><div class="subject-progress-grid">
      <div class="subject-progress-hours"><div class="subject-hour-total" [style.color]="s.color">{{store.hours(s)}}<span>/ {{s.targetHours}} h</span></div><div class="progress-track"><span [style.background]="s.color" [style.width.%]="store.progress(s)"></span></div>
        <figure class="plan-chart"><figcaption><span>Last {{planDays().length}} days</span><span class="plan-legend"><span><i class="plan-bar-planned"></i>Planned</span><span><i [style.background]="s.color"></i>Recorded</span></span></figcaption>
          <div class="plan-chart-days" role="img" [attr.aria-label]="planSummary()">@for(d of planDays();track d.date){<div class="plan-chart-day" [title]="dayTitle(d)"><div class="plan-chart-pair"><span class="plan-bar-planned" [style.height.%]="d.planned/planMax()*100"></span><span [style.background]="s.color" [style.height.%]="d.recorded/planMax()*100"></span></div><small>{{weekday(d.date)}}</small></div>}</div>
          <p>{{planTotals().recorded}} h recorded of {{planTotals().planned}} h planned</p></figure>
      </div>
      <div class="subject-progress-summary"><div class="summary-pair"><span>{{store.remaining(s)<0?'Above target':'Hours remaining'}}</span><strong>{{abs(store.remaining(s))}} h</strong></div><div class="summary-pair"><span>Selected week</span><strong>{{store.hours(s,store.week())}} h</strong></div>@if(stat();as st){<div class="summary-pair"><span>Pace</span><strong [class]="'pace-'+st.status">{{statusLabel[st.status]}}</strong></div><div class="summary-pair"><span>Exam</span><strong>{{examLabel(st.daysToExam)}}</strong></div><div class="summary-pair"><span>Needed per day</span><strong>{{neededLabel(st.neededPerDay)}}</strong></div><div class="summary-pair"><span>Planned ahead</span><strong>{{st.plannedAhead}} h</strong></div>}<div class="summary-pair"><span>Plan kept, last {{planDays().length}} days</span><strong>{{planKept()===null?'—':planKept()+'%'}}</strong></div><a class="button secondary" routerLink="/schedule">Open schedule <app-icon name="arrow" /></a></div>
      <div class="subject-flashcards"><h3>Flashcards</h3>
        @if(scheduler.analyticsError()){<p class="form-error" role="alert">{{scheduler.analyticsError()}}</p>}
        @if(recall();as r){
          <div class="deck-progress"><div class="stacked-bar" [attr.aria-label]="r.total.mature+' mature, '+r.total.learned+' learned, '+r.total.left+' left'"><span class="snapshot-mature" [style.width.%]="r.total.total?r.total.mature/r.total.total*100:0"></span><span class="snapshot-learned" [style.width.%]="r.total.total?r.total.learned/r.total.total*100:0"></span><span class="snapshot-left" [style.width.%]="r.total.total?r.total.left/r.total.total*100:0"></span></div><p>{{r.total.mature}} mature · {{r.total.learned}} learned · {{r.total.left}} left</p></div>
          <dl class="flashcard-figures"><div><dt>Due now</dt><dd>{{r.root.due_cards}}</dd></div><div><dt>Reviews</dt><dd>{{r.root.reviews}}</dd></div><div><dt>Success</dt><dd>{{r.root.success_rate===null?'—':round(r.root.success_rate*100)+'%'}}</dd></div></dl>
          @if(r.parts.length){<ul id="flashcard-decks" class="flashcard-decks" aria-label="Flashcards by folder and deck">@for(item of shownParts(r.parts);track item.row.label){<li [title]="item.snapshot.mature+' mature · '+item.snapshot.learned+' learned · '+item.snapshot.left+' left'"><span class="flashcard-deck-name">{{item.row.name}}</span><div class="stacked-bar" [attr.aria-label]="item.snapshot.mature+' mature, '+item.snapshot.learned+' learned, '+item.snapshot.left+' left'"><span class="snapshot-mature" [style.width.%]="item.snapshot.total?item.snapshot.mature/item.snapshot.total*100:0"></span><span class="snapshot-learned" [style.width.%]="item.snapshot.total?item.snapshot.learned/item.snapshot.total*100:0"></span><span class="snapshot-left" [style.width.%]="item.snapshot.total?item.snapshot.left/item.snapshot.total*100:0"></span></div><span class="flashcard-deck-count">{{item.snapshot.total-item.snapshot.left}}/{{item.snapshot.total}}</span></li>}</ul>
            @if(r.parts.length>deckLimit){<button type="button" class="text-button flashcard-decks-toggle" aria-controls="flashcard-decks" [attr.aria-expanded]="allDecks()" (click)="allDecks.set(!allDecks())">{{allDecks()?'Show fewer':'Show all '+r.parts.length}}<app-icon name="down" /></button>}}
        } @else {<p class="muted">No flashcards yet. Generate cards from a PDF in Materials.</p>}
      </div>
    </div></section>
    <div class="subject-workspace"><app-material-library [subjectId]="s.id" />
      <aside class="subject-sidebar">
        <app-task-list [subjectId]="s.id" />
      </aside>
    </div>
    <dialog #detailsDialog class="edit-dialog subject-details-dialog" aria-labelledby="details-title"><div class="dialog-top"><span class="eyebrow">SUBJECT DETAILS</span><button class="icon-button" aria-label="Close subject details" (click)="detailsDialog.close()"><app-icon name="close" /></button></div>
      <h2 id="details-title">{{s.name}}</h2><p class="muted">Your goals and course information.</p>
      <form (ngSubmit)="save(detailsDialog)"><div class="form-grid"><label>Target study hours<input type="number" name="target" min="0" max="5000" step="0.25" required [(ngModel)]="target"></label><label>Exam date<input type="date" name="exam" required [(ngModel)]="examDate"></label></div>
        <dl class="catalogue-facts"><div><dt>ECTS</dt><dd>{{s.ects ?? '–'}}</dd></div><div><dt>Lecture ID</dt><dd>{{s.lectureId || '–'}}</dd></div><div class="catalogue-homepage"><dt>Homepage</dt><dd>@if(s.homepage){<a [href]="s.homepage" target="_blank" rel="noopener noreferrer">{{s.homepage}}</a>}@else{–}</dd></div></dl>
        <p class="field-hint">From the ETH course catalogue; these cannot be changed here.</p>
        <label class="checkbox-label"><input type="checkbox" name="completed" [(ngModel)]="completed">Subject completed</label>
        @if(error()){<p class="form-error" role="alert">{{error()}}</p>}
        <div class="action-buttons"><button class="button primary" type="submit">Save details <app-icon name="check" /></button><button class="text-button" type="button" (click)="detailsDialog.close()">Cancel</button></div>
      </form>
    </dialog>
  } @else if(!store.loaded()) {<div class="empty-state"><p class="muted">Loading your subject…</p></div>
  } @else {<div class="empty-state"><h1>Subject not found</h1><p class="muted">It is not one of your {{store.data().semester}} courses. Add courses with + in the sidebar.</p><a routerLink="/" class="button primary">Back to overview</a></div>}
`})
export class SubjectComponent {
  readonly store=inject(StudyStore);private readonly route=inject(ActivatedRoute);
  private readonly params=toSignal(this.route.paramMap,{initialValue:this.route.snapshot.paramMap});
  readonly subject=computed(()=>this.store.subjects().find(s=>s.id===this.params().get('id')));
  readonly scheduler=inject(SchedulerService);private readonly materials=inject(MaterialStore);
  /** This subject's own flashcards: the subject total and its top-level folders and decks. */
  readonly recall=computed(()=>{
    const id=this.subject()?.id,rows=this.scheduler.analytics().filter(row=>row.path[0]===id);
    const root=rows.find(row=>row.path.length===1);
    if(!root?.cards)return null;
    const parts=rows.filter(row=>row.path.length===2&&row.cards).sort((a,b)=>a.name.localeCompare(b.name)).map(row=>({row,snapshot:recallSnapshot(row)}));
    return {root,total:recallSnapshot(root),parts};
  });
  readonly round=Math.round;
  /** Planned (calendar) against recorded hours for this subject over the last days of the phase. */
  private readonly asOf=computed(()=>asOfDate(this.store.data(),localToday()));
  readonly planDays=computed(()=>{const id=this.subject()?.id;return id?recentPlanVsRecorded(this.store.data(),id,this.asOf()):[];});
  /** Share of the planned hours that were recorded on their day (extra hours do not count), as on the analytics page. */
  readonly planKept=computed(()=>{const planned=this.planDays().reduce((sum,d)=>sum+d.planned,0);return planned?Math.round(this.planDays().reduce((sum,d)=>sum+Math.min(d.recorded,d.planned),0)/planned*100):null;});
  readonly stat=computed(()=>subjectStats(this.store.data(),this.asOf()).find(st=>st.subject.id===this.subject()?.id));
  readonly statusLabel:Record<SubjectStat['status'],string>={done:'Done','on-track':'On track',behind:'Behind','at-risk':'At risk'};
  neededLabel(hours:number):string{return Number.isFinite(hours)?hours+' h':'—';}
  examLabel(days:number):string{return days<0?'Passed':days===0?'Today':days===1?'Tomorrow':`In ${days} days`;}
  readonly planMax=computed(()=>Math.max(1,...this.planDays().flatMap(d=>[d.planned,d.recorded])));
  readonly planTotals=computed(()=>({planned:round1(this.planDays().reduce((sum,d)=>sum+d.planned,0)),recorded:round1(this.planDays().reduce((sum,d)=>sum+d.recorded,0))}));
  readonly planSummary=computed(()=>this.planDays().map(d=>this.dayTitle(d)).join('; '));
  weekday(iso:string):string{return new Intl.DateTimeFormat('en-GB',{weekday:'short',timeZone:'UTC'}).format(new Date(iso+'T12:00:00Z'));}
  dayTitle(d:PlanVsRecordedDay):string{return `${new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(d.date+'T12:00:00Z'))}: ${d.recorded} h recorded, ${d.planned} h planned`;}
  /** The deck list shows this many until expanded, so many decks do not stretch the card. */
  readonly deckLimit=5;readonly allDecks=signal(false);
  shownParts<T>(parts:T[]):T[]{return this.allDecks()?parts:parts.slice(0,this.deckLimit);}
  private readonly details=computed(()=>{
    const s=this.subject();return s?{id:s.id,targetHours:s.targetHours,examDate:s.examDate,completed:s.completed}:null;
  },{equal:(a,b)=>JSON.stringify(a)===JSON.stringify(b)});
  target:number|null=0;examDate='';completed=false;
  readonly error=signal('');readonly abs=Math.abs;
  constructor(){
    // New decks and cards change the numbers; ratings refresh them through SchedulerService.review().
    effect(()=>{this.materials.files();void this.scheduler.refreshAnalytics();});
    effect(()=>{this.params();this.allDecks.set(false);});
    effect(()=>{const s=this.details();if(s){this.target=s.targetHours;this.examDate=s.examDate;this.completed=s.completed;this.error.set('');}});
  }
  /** Opens the details with the saved values, so a cancelled edit leaves nothing behind. */
  openDetails(dialog:HTMLDialogElement):void {const s=this.subject();if(!s)return;this.target=s.targetHours;this.examDate=s.examDate;this.completed=s.completed;this.error.set('');dialog.showModal();}
  save(dialog:HTMLDialogElement):void {const s=this.subject();if(!s)return;try{if(this.target===null)throw new Error('Enter target hours.');this.store.updateSubject(s.id,{targetHours:this.target,examDate:this.examDate,completed:this.completed});this.error.set('');dialog.close();}catch(e){this.error.set((e as Error).message);}}
}

/** Today in the browser's time zone; the plan's dates are plain calendar days. */
function localToday():string {
  const now=new Date();
  return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
