import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { StudyStore } from '../services/study-store';
import { MaterialStore } from '../services/material-store';
import { StudyDemoService } from '../services/study-demo.service';
import { IconComponent } from '../shared/icon.component';
import { MaterialLibraryComponent } from '../components/material-library.component';
import { TaskListComponent } from '../components/task-list.component';

@Component({standalone:true,imports:[RouterLink,FormsModule,IconComponent,MaterialLibraryComponent,TaskListComponent],template:`
  @if(subject();as s){
    <header class="page-heading"><div><div class="breadcrumb">YOUR WORKSPACE <span>/</span> SUBJECTS</div><h1><span class="subject-dot heading-dot" [style.background]="s.color"></span>{{s.name}}<span>.</span></h1>
      <div class="subject-meta"><span>{{s.lectureId || 'Lecture ID not set'}}</span><span>{{s.ects===undefined?'ECTS not set':s.ects+' ECTS'}}</span>@if(s.homepage){<a [href]="s.homepage" target="_blank" rel="noopener noreferrer">Course catalogue ↗</a>}</div>
    </div><button class="button primary" (click)="store.openEditor(s.id)"><app-icon name="plus" /> Record hours</button></header>
    <div class="subject-workspace"><app-material-library [subjectId]="s.id" />
      <aside class="subject-sidebar">
        <app-task-list [subjectId]="s.id" />
        <section class="panel subject-form"><div class="panel-heading"><div><h2>Subject details</h2><p>Your goals and course information.</p></div><app-icon name="book" /></div>
          <form (ngSubmit)="save()"><div class="form-grid"><label>Target study hours<input type="number" name="target" min="0" max="5000" step="0.25" required [(ngModel)]="target"></label><label>Exam date<input type="date" name="exam" required [(ngModel)]="examDate"></label></div>
            <div class="form-grid"><label>ECTS<input name="ects" readonly [value]="s.ects ?? '–'"></label><label>Lecture ID<input name="lecture" readonly [value]="s.lectureId || '–'"></label></div>
            <label>Subject homepage<input name="homepage" readonly [value]="s.homepage || '–'"></label><p class="field-hint">ECTS, lecture ID and homepage come from the ETH course catalogue.</p>
            <label class="checkbox-label"><input type="checkbox" name="completed" [(ngModel)]="completed">Subject completed</label>
            @if(error()){<p class="form-error" role="alert">{{error()}}</p>}<button class="button primary" type="submit">Save details <app-icon name="check" /></button>
          </form>
        </section>
        <section class="panel action-panel"><div class="panel-heading"><div><span class="eyebrow">ONE STEP AT A TIME</span><h2>Next action</h2></div><app-icon name="arrow" /></div>
          <label class="sr-only" for="next-action">Next action</label><textarea id="next-action" rows="3" maxlength="1000" [(ngModel)]="nextAction" placeholder="What will you work on next?"></textarea>
          <div class="action-buttons"><button class="button secondary" [disabled]="suggesting()" (click)="suggest()">{{suggesting()?'Suggesting…':'Suggest next action'}}</button><button class="text-button" (click)="saveAction()">Save action</button></div>
          <p class="field-hint">Suggestions use a local demo.</p>
          @if(suggestion()){<div class="suggestion-preview"><span class="demo-badge">Demo suggestion</span><label for="suggestion">Proposed next action</label><textarea id="suggestion" rows="4" maxlength="1000" [ngModel]="suggestion()" (ngModelChange)="suggestion.set($event)"></textarea><div class="action-buttons"><button class="button primary" (click)="acceptSuggestion()">Use this action</button><button class="text-button" (click)="suggestion.set('')">Dismiss</button></div></div>}
          @if(actionError()){<p class="form-error" role="alert">{{actionError()}}</p>}
        </section>
        <section class="panel subject-progress"><span class="eyebrow">SUBJECT ANALYTICS</span><h2>Your progress</h2><div class="subject-hour-total" [style.color]="s.color">{{store.hours(s)}}<span>/ {{s.targetHours}} h</span></div><div class="progress-track"><span [style.background]="s.color" [style.width.%]="store.progress(s)"></span></div>
          <div class="summary-pair"><span>{{store.remaining(s)<0?'Above target':'Hours remaining'}}</span><strong>{{abs(store.remaining(s))}} h</strong></div><div class="summary-pair"><span>Selected week</span><strong>{{store.hours(s,store.week())}} h</strong></div>
          <div class="anki-subject"><h3>Anki progress</h3>@for(deck of decks();track deck.name){<div class="deck-progress"><strong>{{deck.name}}</strong><div class="stacked-bar" [attr.aria-label]="deck.mature+' mature, '+deck.learned+' learned, '+deck.left+' left'"><span style="background:#315c47" [style.width.%]="deck.total?deck.mature/deck.total*100:0"></span><span style="background:#a1b7a5" [style.width.%]="deck.total?deck.learned/deck.total*100:0"></span><span style="background:#ede9dc" [style.width.%]="deck.total?deck.left/deck.total*100:0"></span></div><p>{{deck.mature}} mature · {{deck.learned}} learned · {{deck.left}} left</p></div>}@empty{<p class="muted">No decks linked to this subject yet.</p>}
          <details class="deck-links"><summary>Manage linked decks</summary>@for(deck of availableDecks();track deck.name){<label class="checkbox-label"><input type="checkbox" [checked]="deck.subjectId===s.id" (change)="store.linkDeck(deck.name, $any($event.target).checked?s.id:'')">{{deck.name}}</label>}@empty{<p class="muted">No unassigned decks available.</p>}</details><p class="field-hint">Imported Anki snapshot. No live connection.</p></div>
          <a class="button secondary" routerLink="/schedule">Open schedule <app-icon name="arrow" /></a>
        </section>
      </aside>
    </div>
  } @else if(!store.loaded()) {<div class="empty-state"><p class="muted">Loading your subject…</p></div>
  } @else {<div class="empty-state"><h1>Subject not found</h1><p class="muted">It is not one of your {{store.data().semester}} courses. Add courses with + in the sidebar.</p><a routerLink="/" class="button primary">Back to overview</a></div>}
`})
export class SubjectComponent {
  readonly store=inject(StudyStore);private readonly route=inject(ActivatedRoute);private readonly materials=inject(MaterialStore);private readonly demo=inject(StudyDemoService);
  private readonly params=toSignal(this.route.paramMap,{initialValue:this.route.snapshot.paramMap});
  readonly subject=computed(()=>this.store.subjects().find(s=>s.id===this.params().get('id')));
  readonly decks=computed(()=>this.store.data().anki.filter(d=>d.subjectId===this.subject()?.id));
  readonly availableDecks=computed(()=>this.store.data().anki.filter(d=>!d.subjectId||d.subjectId===this.subject()?.id));
  private readonly details=computed(()=>{
    const s=this.subject();return s?{id:s.id,targetHours:s.targetHours,examDate:s.examDate,completed:s.completed}:null;
  },{equal:(a,b)=>JSON.stringify(a)===JSON.stringify(b)});
  private readonly savedAction=computed(()=>({id:this.subject()?.id,text:this.subject()?.nextAction??''}),{equal:(a,b)=>a.id===b.id&&a.text===b.text});
  target:number|null=0;examDate='';nextAction='';completed=false;
  readonly error=signal('');readonly actionError=signal('');readonly suggestion=signal('');readonly suggesting=signal(false);readonly abs=Math.abs;
  constructor(){
    effect(()=>{const s=this.details();if(s){this.target=s.targetHours;this.examDate=s.examDate;this.completed=s.completed;this.error.set('');}});
    effect(()=>{this.nextAction=this.savedAction().text;});
    effect(()=>{this.params();this.suggestion.set('');this.actionError.set('');});
  }
  save():void {const s=this.subject();if(!s)return;try{if(this.target===null)throw new Error('Enter target hours.');this.store.updateSubject(s.id,{targetHours:this.target,examDate:this.examDate,completed:this.completed});this.error.set('');}catch(e){this.error.set((e as Error).message);}}
  saveAction():void{const s=this.subject();if(!s)return;try{this.store.updateSubject(s.id,{nextAction:this.nextAction.trim()});this.actionError.set('');}catch(e){this.actionError.set((e as Error).message);}}
  async suggest():Promise<void>{const s=this.subject();if(!s)return;this.suggesting.set(true);this.actionError.set('');try{const file=this.materials.files().find(f=>f.subjectId===s.id&&f.kind!=='folder'&&(f.marker==='Revisit'||f.marker==='To read'));const value=await this.demo.suggest(s.name,file?.name);if(this.subject()?.id===s.id)this.suggestion.set(value);}catch{this.actionError.set('Could not create a suggestion. Try again.');}finally{this.suggesting.set(false);}}
  acceptSuggestion():void{this.nextAction=this.suggestion();this.saveAction();if(!this.actionError())this.suggestion.set('');}
}
