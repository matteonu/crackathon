import { Component, computed, input, output, signal } from '@angular/core';
import { FolderCard } from '../models/material';
@Component({selector:'app-folder-flashcards',standalone:true,template:`
  <div class="folder-card-heading"><div><span class="eyebrow">FOLDER FLASHCARDS</span><h2>{{name()}}</h2><p class="muted">{{cards().length}} cards · includes all nested folders</p></div>@if(mode()==='list'){<button class="button primary" [disabled]="!cards().length" (click)="start()">Start learning</button>}@else{<button class="button secondary" (click)="mode.set('list')">View all cards</button>}</div>
  @if(mode()==='list'){
    <div class="folder-card-list">@for(card of cards();track card.key){<details class="folder-card-item"><summary><span><strong>{{card.question}}</strong><small>{{card.fileName}} @if(card.demo){ · Demo card}</small></span></summary><p>{{card.answer}}</p><button class="text-button" (click)="openFile.emit(card.fileId)">Open source file →</button></details>}@empty{<div class="empty-state">This folder has no flashcards yet. Open a file to generate or write some.</div>}</div>
  }@else if(current();as card){
    <div class="learning-progress"><span>{{learned()}} / {{cards().length}} learned</span><span>{{queue().length}} remaining</span></div>
    <article class="learning-card"><span class="eyebrow">{{card.fileName}}</span>@if(card.demo){<span class="demo-badge">Demo card</span>}<h3>{{card.question}}</h3>@if(revealed()){<p class="learning-answer">{{card.answer}}</p><div class="learning-actions"><button class="button secondary" (click)="rate(false)">Review again</button><button class="button primary" (click)="rate(true)">Got it</button></div>}@else{<button class="button primary" (click)="revealed.set(true)">Reveal answer</button>}</article><p class="field-hint">Learning progress lasts for this practice session.</p>
  }@else{<div class="learning-complete"><span>✓</span><h3>All {{learned()}} cards reviewed</h3><p>Ready for another round?</p><button class="button primary" (click)="start()">Start again</button></div>}
`})
export class FolderFlashcardsComponent {
  readonly cards=input.required<FolderCard[]>();readonly name=input.required<string>();readonly openFile=output<string>();
  readonly mode=signal<'list'|'learn'>('list');readonly queue=signal<FolderCard[]>([]);readonly learned=signal(0);readonly revealed=signal(false);readonly current=computed(()=>this.queue()[0]);
  start():void{this.queue.set([...this.cards()]);this.learned.set(0);this.revealed.set(false);this.mode.set('learn');}
  rate(known:boolean):void{const card=this.current();if(!card)return;this.queue.update(q=>known?q.slice(1):[...q.slice(1),card]);if(known)this.learned.update(n=>n+1);this.revealed.set(false);}
}
