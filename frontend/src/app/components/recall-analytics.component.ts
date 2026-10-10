import { Component, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { SchedulerService } from '../services/scheduler.service';
import { MaterialStore } from '../services/material-store';
import { StudyStore } from '../services/study-store';
import { RecallAnalytics, recallKey, recallTreeRows } from '../models/recall';
import { IconComponent } from '../shared/icon.component';

@Component({selector:'app-recall-analytics',standalone:true,imports:[DecimalPipe,IconComponent],templateUrl:'./recall-analytics.component.html'})
export class RecallAnalyticsComponent {
  readonly scheduler=inject(SchedulerService);private readonly materials=inject(MaterialStore);private readonly study=inject(StudyStore);
  readonly detailDialog=viewChild<ElementRef<HTMLDialogElement>>('detailDialog');
  readonly expanded=signal(new Set([recallKey([])]));readonly selectedKey=signal<string|null>(null);
  readonly rows=computed(()=>recallTreeRows(this.scheduler.analytics(),this.expanded()));
  readonly selected=computed(()=>this.scheduler.analytics().find(row=>recallKey(row.path)===this.selectedKey()));
  readonly ratingBars=computed(()=>{
    const row=this.selected();return row?(['again','hard','good','easy'] as const).map(key=>({label:key[0].toUpperCase()+key.slice(1),value:row.ratings[key],percent:row.reviews?row.ratings[key]/row.reviews*100:0,color:'rating-'+key})):[];
  });
  readonly stateBars=computed(()=>{
    const row=this.selected();return row?(['new','learning','relearning','review'] as const).map(key=>({label:key[0].toUpperCase()+key.slice(1),value:row.states[key],percent:row.cards?row.states[key]/row.cards*100:0,color:'state-'+key})):[];
  });
  constructor(){effect(()=>{this.materials.files();void this.scheduler.refreshAnalytics();});}
  toggle(key:string):void{this.expanded.update(old=>{const next=new Set(old);next.has(key)?next.delete(key):next.add(key);return next;});}
  showDetails(row:RecallAnalytics):void{this.selectedKey.set(recallKey(row.path));this.detailDialog()?.nativeElement.showModal();}
  name(row:RecallAnalytics):string{return row.path.length===1?this.study.subjects().find(s=>s.id===row.path[0])?.name??row.name:row.name;}
  label(value:string):string{const [subject,...rest]=value.split(' / ');return [this.study.subjects().find(s=>s.id===subject)?.name??subject,...rest].join(' / ');}
}
