import { Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { StudyStore } from '../services/study-store';
import { CourseHit } from '../models/semester';
import { IconComponent } from '../shared/icon.component';
import { LoadingDotsComponent } from '../shared/loading-dots.component';

/** The + in the sidebar: search the VVZ courses offered this semester and add them. */
@Component({selector:'app-course-search-dialog',standalone:true,imports:[IconComponent,LoadingDotsComponent],template:`
  <dialog #dialog class="edit-dialog course-search-dialog" aria-labelledby="course-search-title" (close)="clear()">
    <div class="dialog-top"><span class="eyebrow">FROM THE ETH COURSE CATALOGUE</span><button type="button" class="icon-button" aria-label="Close" (click)="dialog.close()"><app-icon name="close" /></button></div>
    <h2 id="course-search-title">Add a course to {{store.data().semester}}</h2>
    <label class="sr-only" for="course-search">Search by title or course number</label>
    <input #input id="course-search" type="search" autocomplete="off" maxlength="100" placeholder="Search by title or number, e.g. Analysis or 252-0026"
      [value]="query()" (input)="typed($any($event.target).value)">
    <div class="course-results" aria-live="polite">
      @if(error()){<p class="form-error" role="alert">{{error()}}</p>}
      @if(query().trim().length < 2){<p class="field-hint">Type at least 2 characters. Only courses offered in {{store.data().semester}} are shown.</p>}
      @else if(searching()){<p class="field-hint"><app-loading-dots label="Searching" /></p>}
      @else if(!hits().length && !error()){<p class="field-hint">No courses match “{{query().trim()}}” in {{store.data().semester}}.</p>}
      <ul>@for(hit of hits();track hit.id){
        <li class="course-hit"><div><strong>{{hit.title}}</strong><span>{{hit.code}}@if(hit.ects!==null){ · {{hit.ects}} ECTS}@if(hit.professor){ · {{hit.professor}}}</span></div>
          <button type="button" class="button secondary" [disabled]="hit.added || adding()===hit.id" (click)="add(hit)">
            @if(hit.added){<app-icon name="check" /> Added}@else if(adding()===hit.id){Adding…}@else{<app-icon name="plus" /> Add}</button></li>
      }</ul>
    </div>
  </dialog>
`})
export class CourseSearchDialogComponent {
  readonly store=inject(StudyStore);
  readonly dialog=viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  readonly input=viewChild.required<ElementRef<HTMLInputElement>>('input');
  readonly query=signal('');readonly hits=signal<CourseHit[]>([]);readonly searching=signal(false);readonly error=signal('');readonly adding=signal<number|null>(null);
  private timer?:ReturnType<typeof setTimeout>;private latest=0;

  open():void{this.dialog().nativeElement.showModal();this.input().nativeElement.focus();}
  clear():void{clearTimeout(this.timer);this.latest++;this.query.set('');this.hits.set([]);this.error.set('');this.searching.set(false);}
  typed(value:string):void{
    this.query.set(value);this.error.set('');clearTimeout(this.timer);
    const q=value.trim();
    if(q.length<2){this.latest++;this.hits.set([]);this.searching.set(false);return;}
    this.searching.set(true);
    this.timer=setTimeout(()=>void this.search(q),250);
  }
  private async search(q:string):Promise<void>{
    const run=++this.latest;
    try{const hits=await this.store.searchCourses(q);if(run===this.latest)this.hits.set(hits);}
    catch(e){if(run===this.latest){this.hits.set([]);this.error.set(e instanceof Error?e.message:'The search failed. Please retry.');}}
    finally{if(run===this.latest)this.searching.set(false);}
  }
  async add(hit:CourseHit):Promise<void>{
    this.adding.set(hit.id);this.error.set('');
    try{await this.store.addCourse(hit);this.hits.update(list=>list.map(h=>h.id===hit.id?{...h,added:true}:h));}
    catch(e){this.error.set(e instanceof Error?e.message:'Could not add this course. Please retry.');}
    finally{this.adding.set(null);}
  }
}
