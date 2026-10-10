import { Component, ElementRef, Injector, afterNextRender, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TaskStore } from '../services/task-store';
import { Task, MAX_TASK_NOTES, MAX_TASK_TITLE, doneTasks, dueLabel, dueState, openTasks } from '../models/task';
import { IconComponent } from '../shared/icon.component';

/** The subject's to-do list: add on Enter, tick off, click a row to edit, reorder, clear completed. */
@Component({selector:'app-task-list',standalone:true,imports:[FormsModule,IconComponent],template:`
  <section class="panel task-panel">
    <div class="panel-heading"><div><span class="eyebrow">TASKS</span><h2>To-do</h2><p>{{open().length}} open @if(done().length){· {{done().length}} done}</p></div><app-icon name="check" /></div>
    <form class="task-add" (ngSubmit)="add()">
      <label class="sr-only" for="task-title">New to-do</label>
      <input id="task-title" name="title" [(ngModel)]="draft" [maxlength]="maxTitle" placeholder="Add a to-do and press Enter" autocomplete="off" [disabled]="store.loading()">
      <button class="button primary" type="submit" [disabled]="!draft.trim()||store.loading()" aria-label="Add to-do"><app-icon name="plus" /></button>
    </form>
    @if(store.error()){<p class="form-error" role="alert">{{store.error()}}</p>}
    @if(store.loading()){<p class="muted task-empty">Loading your to-dos…</p>}
    <ul class="task-list" aria-label="Open to-dos">
      @for(t of open();track t.id;let i=$index){
        <li class="task" [class.task-editing]="editingId()===t.id" (click)="rowClick($event,t)">
          <input type="checkbox" class="task-check" [checked]="t.done" (change)="store.toggle(t.id)" [attr.aria-label]="'Mark '+t.title+' as done'">
          @if(editingId()===t.id){
            <form class="task-edit task-fade" (ngSubmit)="saveEdit($event,t)">
              <label class="sr-only" for="edit-title">Title</label>
              <input #titleBox id="edit-title" name="title" [(ngModel)]="editTitle" [maxlength]="maxTitle" required (keydown.escape)="cancelEdit($event)">
              <label class="sr-only" for="edit-notes">Notes</label>
              <textarea id="edit-notes" name="notes" rows="2" [(ngModel)]="editNotes" [maxlength]="maxNotes" placeholder="Notes" (keydown.escape)="cancelEdit($event)"></textarea>
              <div class="task-edit-row">
                <label class="task-due-field">Due<input type="date" name="due" [(ngModel)]="editDue"></label>
                <div class="action-buttons"><button class="button primary" type="submit" [disabled]="!editTitle.trim()">Save</button><button class="text-button" type="button" (click)="cancelEdit($event)">Cancel</button></div>
              </div>
            </form>
          } @else {
            <div class="task-body task-fade">
              <span class="task-title">{{t.title}}</span>
              @if(t.notes){<p class="task-notes">{{t.notes}}</p>}
              @if(t.due){<span class="task-due" [class]="'task-due '+dueState(t.due,today())"><app-icon name="calendar" />{{dueLabel(t.due,today())}}</span>}
            </div>
            <div class="task-tools">
              <button type="button" class="task-tool" [disabled]="i===0" (click)="store.move(t.id,-1)" [attr.aria-label]="'Move '+t.title+' up'"><app-icon name="left" /></button>
              <button type="button" class="task-tool" [disabled]="i===open().length-1" (click)="store.move(t.id,1)" [attr.aria-label]="'Move '+t.title+' down'"><app-icon name="right" /></button>
              <button type="button" class="task-tool task-tool-danger" (click)="store.remove(t.id)" [attr.aria-label]="'Delete '+t.title"><app-icon name="trash" /></button>
            </div>
          }
        </li>
      } @empty { @if(!store.loading()){<li class="task-empty muted">Nothing to do yet. Add a to-do above.</li>} }
    </ul>
    @if(done().length){
      <div class="task-completed">
        <button type="button" class="task-completed-toggle" [attr.aria-expanded]="showDone()" aria-controls="task-completed-list" (click)="showDone.set(!showDone())"><span class="task-chevron" [class.open]="showDone()"></span>Completed ({{done().length}})</button>
        <div id="task-completed-list" class="task-collapse" [class.open]="showDone()" [attr.aria-hidden]="!showDone()"><div>
          <ul class="task-list">
            @for(t of done();track t.id){
              <li class="task task-done">
                <input type="checkbox" class="task-check" checked (change)="store.toggle(t.id)" [attr.aria-label]="'Mark '+t.title+' as not done'" [tabindex]="showDone()?0:-1">
                <div class="task-body"><span class="task-title">{{t.title}}</span>@if(t.notes){<p class="task-notes">{{t.notes}}</p>}</div>
                <div class="task-tools"><button type="button" class="task-tool task-tool-danger" (click)="store.remove(t.id)" [attr.aria-label]="'Delete '+t.title" [tabindex]="showDone()?0:-1"><app-icon name="trash" /></button></div>
              </li>
            }
          </ul>
          <button type="button" class="text-button" (click)="store.clearCompleted(subjectId())" [tabindex]="showDone()?0:-1"><app-icon name="trash" /> Delete all completed</button>
        </div></div>
      </div>
    }
  </section>
`})
export class TaskListComponent {
  readonly subjectId=input.required<string>();readonly store=inject(TaskStore);private readonly injector=inject(Injector);
  readonly maxTitle=MAX_TASK_TITLE;readonly maxNotes=MAX_TASK_NOTES;readonly dueState=dueState;readonly dueLabel=dueLabel;
  readonly open=computed(()=>openTasks(this.store.tasks(),this.subjectId()));
  readonly done=computed(()=>doneTasks(this.store.tasks(),this.subjectId()));
  readonly today=signal(localToday());
  readonly editingId=signal<string|null>(null);readonly showDone=signal(false);
  private readonly titleField=viewChild<ElementRef<HTMLInputElement>>('titleBox');
  draft='';editTitle='';editNotes='';editDue='';
  constructor(){
    effect(()=>{this.subjectId();this.editingId.set(null);this.draft='';this.store.error.set('');});
    effect(()=>{const field=this.titleField();if(field&&this.editingId())field.nativeElement.focus();});
  }
  async add():Promise<void>{
    const title=this.draft;this.draft='';this.today.set(localToday());
    if(!(await this.store.add(this.subjectId(),title)))this.draft=title;
  }
  /** Clicking anywhere on a row opens it, except on its own controls (checkbox, tools, the editor). */
  rowClick(event:Event,t:Task):void {
    if(this.editingId()===t.id||(event.target as HTMLElement).closest('input, button, textarea, label, form'))return;
    this.animateRow(event.currentTarget as HTMLElement,()=>{this.editingId.set(t.id);this.editTitle=t.title;this.editNotes=t.notes;this.editDue=t.due??'';});
  }
  cancelEdit(event:Event):void {this.animateRow(rowOf(event),()=>this.editingId.set(null));}
  async saveEdit(event:Event,t:Task):Promise<void>{
    const row=rowOf(event);
    if(await this.store.update(t.id,{title:this.editTitle,notes:this.editNotes,due:this.editDue||null}))this.animateRow(row,()=>this.editingId.set(null));
  }
  /** Apply a state change and tween the row's height from before to after, so opening and
   *  closing the editor both slide instead of jumping. */
  private animateRow(row:HTMLElement|null,change:()=>void):void {
    if(!row||!row.animate||matchMedia('(prefers-reduced-motion: reduce)').matches){change();return;}
    const from=row.getBoundingClientRect().height;
    change();
    afterNextRender(()=>{
      const to=row.getBoundingClientRect().height;if(from===to)return;
      row.style.overflow='hidden';
      row.animate([{height:`${from}px`},{height:`${to}px`}],{duration:260,easing:'cubic-bezier(.2,.7,.2,1)'}).finished.finally(()=>{row.style.overflow='';});
    },{injector:this.injector});
  }
}

function rowOf(event:Event):HTMLElement|null {return (event.target as HTMLElement).closest('.task');}

/** Today in the browser's time zone, as the to-dos' due dates are plain calendar days. */
function localToday():string {
  const now=new Date();
  return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
