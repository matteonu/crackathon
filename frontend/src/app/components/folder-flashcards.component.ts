import { Component, ElementRef, OnDestroy, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { FolderCard, descendants, materialKind } from '../models/material';
import { MaterialStore } from '../services/material-store';
import { PracticeCard, PracticeScope, Rating, RecallAnalytics, SchedulerError, SchedulerService } from '../services/scheduler.service';

@Component({selector:'app-folder-flashcards',standalone:true,imports:[FormsModule,DatePipe],templateUrl:'./folder-flashcards.component.html',host:{'(document:keydown)':'onKeydown($event)'}})
export class FolderFlashcardsComponent implements OnDestroy {
  readonly cards=input.required<FolderCard[]>();readonly name=input.required<string>();readonly subjectId=input.required<string>();
  readonly folderId=input<string|null>(null);readonly deckId=input<string|null>(null);readonly openFile=output<string>();
  readonly learning=input(false);readonly startLearning=output<void>();
  private readonly scheduler=inject(SchedulerService);
  private readonly materials=inject(MaterialStore);
  private readonly element=inject<ElementRef<HTMLElement>>(ElementRef);
  readonly queue=signal<PracticeCard[]>([]);readonly reviewed=signal(0);readonly revealed=signal(false);
  readonly current=computed(()=>this.queue()[0]);readonly busy=signal(false);readonly error=signal('');
  readonly summary=signal<RecallAnalytics|null>(null);
  readonly limit=signal(20);readonly newLimit=signal(5);readonly validLimits=computed(()=>Number.isInteger(this.limit())&&this.limit()>0&&Number.isInteger(this.newLimit())&&this.newLimit()>=0);
  readonly nextDue=signal<string|null>(null);readonly available=signal(false);readonly clock=signal(Date.now());
  readonly dueCount=signal(0);
  readonly ready=computed(()=>this.available()||!!this.nextDue()&&this.clock()>=Date.parse(this.nextDue()!));
  readonly ratings:Rating[]=['again','hard','good','easy'];readonly ratingLabels:Record<Rating,string>={again:'Again',hard:'Hard',good:'Good',easy:'Easy'};
  readonly ratingShortcuts:Record<Rating,string>={again:'1',hard:'2',good:'3 Space',easy:'4'};
  readonly preferenceError=signal('');readonly savingPreference=signal(false);
  readonly preferenceFolders=computed(()=>{
    const files=this.materials.files().filter(f=>f.subjectId===this.subjectId());
    if(this.deckId()){
      const parents=[];const visited=new Set<string>();let parent=files.find(f=>f.id===this.deckId())?.parentId;
      while(parent&&!visited.has(parent)){visited.add(parent);const folder=files.find(f=>f.id===parent);if(!folder)break;parents.unshift(folder);parent=folder.parentId;}
      return parents;
    }
    const selected=files.find(f=>f.id===this.folderId());
    return [...(selected?[selected]:[]),...descendants(files,this.folderId())].filter(f=>materialKind(f)==='folder');
  });
  private batchLimit=20;private batchNewLimit=5;
  private displayedAt=0;private offset=0;private destroyed=false;private readonly timer=setInterval(()=>this.clock.set(Date.now()+this.offset),1000);
  constructor(){
    effect(()=>{if(this.learning())untracked(()=>void this.start());});
    effect(()=>{
      this.limit();this.newLimit();
      if(this.learning())untracked(()=>{
        if(!this.current()&&!this.busy()&&this.validLimits())void this.refreshAvailability();
      });
    });
  }
  ngOnDestroy():void{this.destroyed=true;clearInterval(this.timer);}
  onKeydown(event:KeyboardEvent):void{
    if(!this.learning()||!this.current()||event.defaultPrevented||event.isComposing||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return;
    const dialog=this.element.nativeElement.closest('dialog');if(dialog&&!dialog.open)return;
    if(event.target instanceof Element&&event.target.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="spinbutton"]'))return;
    const space=event.key===' ',rating=this.ratings[Number(event.key)-1];
    if(!space&&!rating)return;
    // Cancel native button activation/scrolling and ignore held keys or pending saves.
    event.preventDefault();if(event.repeat||this.busy())return;
    if(!this.revealed()){if(space)this.revealed.set(true);return;}
    void this.rate(space?'good':rating);
  }
  async setWeight(id:string,value:number):Promise<void>{
    if(!Number.isFinite(value)||value<=0){this.preferenceError.set('Use a finite positive folder weight.');return;}
    this.savingPreference.set(true);this.preferenceError.set('');
    try{if(!await this.materials.update(id,{folderWeight:value}))this.preferenceError.set(this.materials.error());}
    finally{this.savingPreference.set(false);}
  }
  private scope():PracticeScope{return {subjectId:this.subjectId(),folderId:this.folderId(),deckId:this.deckId()};}
  async start():Promise<void>{
    if(this.busy()||!this.validLimits())return;this.busy.set(true);this.error.set('');
    const limit=this.limit(),newLimit=this.newLimit();
    try{const session=await this.scheduler.session(this.scope(),limit,newLimit);if(this.destroyed)return;
      this.batchLimit=limit;this.batchNewLimit=newLimit;
      this.offset=Date.parse(session.serverNow)-Date.now();this.clock.set(Date.now()+this.offset);
      this.queue.set(session.cards);this.reviewed.set(0);this.revealed.set(false);this.nextDue.set(session.nextDue);this.dueCount.set(session.dueCount);this.available.set(false);this.displayedAt=performance.now();
      void this.refreshSummary();
      if(!session.cards.length&&(limit!==this.limit()||newLimit!==this.newLimit()))await this.fetchNext();
    }catch(e){this.error.set(e instanceof Error?e.message:'Could not start learning.');}finally{this.busy.set(false);}
  }
  async rate(rating:Rating):Promise<void>{
    const card=this.current();if(!card||this.busy())return;this.busy.set(true);this.error.set('');
    try{await this.scheduler.review(card,rating,(performance.now()-this.displayedAt)/1000);if(this.destroyed)return;
      this.queue.update(q=>q.slice(1));this.reviewed.update(n=>n+1);this.revealed.set(false);this.displayedAt=performance.now();
      void this.refreshSummary();
      if(!this.queue().length)await this.fetchNext();
    }catch(e){
      this.error.set(e instanceof Error?e.message:'Could not save your rating.');
      if(e instanceof SchedulerError&&e.status===409){
        try{const session=await this.scheduler.session(this.scope(),this.batchLimit,this.batchNewLimit);if(this.destroyed)return;this.queue.set(session.cards);this.nextDue.set(session.nextDue);this.dueCount.set(session.dueCount);this.available.set(false);this.revealed.set(false);this.displayedAt=performance.now();}
        catch(refreshError){this.error.set(refreshError instanceof Error?refreshError.message:'Refresh failed. Try again.');}
      }
      if(e instanceof SchedulerError&&e.status===404){this.queue.set([]);this.available.set(false);this.nextDue.set(null);this.dueCount.set(0);}
    }finally{this.busy.set(false);}
  }
  private async fetchNext():Promise<void>{
    // An unfinished numeric edit must not turn a successfully saved review into an error.
    const limit=this.validLimits()?this.limit():this.batchLimit,newLimit=this.validLimits()?this.newLimit():this.batchNewLimit;
    const session=await this.scheduler.session(this.scope(),limit,newLimit);if(this.destroyed)return;
    if(this.validLimits()&&(limit!==this.limit()||newLimit!==this.newLimit()))return this.fetchNext();
    this.nextDue.set(session.nextDue);this.dueCount.set(session.dueCount);this.available.set(session.cards.length>0);
  }
  private async refreshSummary():Promise<void>{try{const rows=await this.scheduler.statistics(this.scope());if(!this.destroyed)this.summary.set(rows[0]??null);}catch{/* Review errors are shown separately; summary can refresh next time. */}}
  private async refreshAvailability():Promise<void>{if(this.busy()||!this.validLimits())return;this.busy.set(true);this.error.set('');try{await this.fetchNext();}catch(e){this.error.set(e instanceof Error?e.message:'Could not load the next session.');}finally{this.busy.set(false);}}
  delay(seconds:number):string{const days=Math.round(seconds/86400*10)/10;return seconds<3600?`${Math.round(seconds/60*10)/10} min`:seconds<86400?`${Math.round(seconds/3600*10)/10} h`:`${days} ${days===1?'day':'days'}`;}
}
