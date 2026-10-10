import { Component, ElementRef, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TaskStore } from '../services/task-store';
import { Task, MAX_TASK_NOTES, MAX_TASK_TITLE, doneTasks, dueLabel, dueState, openTasks } from '../models/task';
import { IconComponent } from '../shared/icon.component';

/** The subject's to-do list: add on Enter, tick off, click a title to edit, reorder, clear completed. */
@Component({selector:'app-task-list',standalone:true,imports:[FormsModule,IconComponent],template:`
  <section class="panel task-panel">
    <div class="panel-heading"><div><span class="eyebrow">TASKS</span><h2>To do</h2><p>{{open().length}} open @if(done().length){· {{done().length}} done}</p></div><app-icon name="check" /></div>
    <form class="task-add" (ngSubmit)="add()">
      <label class="sr-only" for="task-title">New task</label>
      <input id="task-title" name="title" [(ngModel)]="draft" [maxlength]="maxTitle" placeholder="Add a task and press Enter" autocomplete="off" [disabled]="store.loading()">
      <button class="button primary" type="submit" [disabled]="!draft.trim()||store.loading()" aria-label="Add task"><app-icon name="plus" /></button>
    </form>
    @if(store.error()){<p class="form-error" role="alert">{{store.error()}}</p>}
    @if(store.loading()){<p class="muted task-empty">Loading your tasks…</p>}
    <ul class="task-list" [attr.aria-label]="'Open tasks'">
      @for(t of open();track t.id;let i=$index){
        <li class="task" [class.task-editing]="editingId()===t.id">
          <input type="checkbox" class="task-check" [checked]="t.done" (change)="store.toggle(t.id)" [attr.aria-label]="'Mark '+t.title+' as done'">
          @if(editingId()===t.id){
            <form class="task-edit" (ngSubmit)="saveEdit(t)">
              <label class="sr-only" for="edit-title">Title</label>
              <input #titleBox id="edit-title" name="title" [(ngModel)]="editTitle" [maxlength]="maxTitle" required (keydown.escape)="cancelEdit()">
              <label class="sr-only" for="edit-notes">Notes</label>
              <textarea id="edit-notes" name="notes" rows="2" [(ngModel)]="editNotes" [maxlength]="maxNotes" placeholder="Notes" (keydown.escape)="cancelEdit()"></textarea>
              <div class="task-edit-row">
                <label class="task-due-field">Due<input type="date" name="due" [(ngModel)]="editDue"></label>
                <div class="action-buttons"><button class="button primary" type="submit" [disabled]="!editTitle.trim()">Save</button><button class="text-button" type="button" (click)="cancelEdit()">Cancel</button></div>
              </div>
            </form>
          } @else {
            <div class="task-body">
              <button type="button" class="task-title" (click)="startEdit(t)" [attr.aria-label]="'Edit '+t.title">{{t.title}}</button>
              @if(t.notes){<p class="task-notes">{{t.notes}}</p>}
              @if(t.due){<span class="task-due" [class]="'task-due '+dueState(t.due,today())"><app-icon name="calendar" />{{dueLabel(t.due,today())}}</span>}
            </div>
            <div class="task-tools">
              <button type="button" class="icon-button small" [disabled]="i===0" (click)="store.move(t.id,-1)" [attr.aria-label]="'Move '+t.title+' up'"><app-icon name="left" /></button>
              <button type="button" class="icon-button small" [disabled]="i===open().length-1" (click)="store.move(t.id,1)" [attr.aria-label]="'Move '+t.title+' down'"><app-icon name="right" /></button>
              <button type="button" class="icon-button small" (click)="store.remove(t.id)" [attr.aria-label]="'Delete '+t.title"><app-icon name="trash" /></button>
            </div>
          }
        </li>
      } @empty { @if(!store.loading()){<li class="task-empty muted">Nothing to do yet. Add a task above.</li>} }
    </ul>
    @if(done().length){
      <details class="task-completed" [open]="showDone()" (toggle)="showDone.set($any($event.target).open)">
        <summary>Completed ({{done().length}})</summary>
        <ul class="task-list">
          @for(t of done();track t.id){
            <li class="task task-done">
              <input type="checkbox" class="task-check" checked (change)="store.toggle(t.id)" [attr.aria-label]="'Mark '+t.title+' as not done'">
              <div class="task-body"><span class="task-title">{{t.title}}</span>@if(t.notes){<p class="task-notes">{{t.notes}}</p>}</div>
              <div class="task-tools"><button type="button" class="icon-button small" (click)="store.remove(t.id)" [attr.aria-label]="'Delete '+t.title"><app-icon name="trash" /></button></div>
            </li>
          }
        </ul>
        <button type="button" class="text-button" (click)="store.clearCompleted(subjectId())"><app-icon name="trash" /> Delete all completed</button>
      </details>
    }
  </section>
`})
export class TaskListComponent {
  readonly subjectId=input.required<string>();readonly store=inject(TaskStore);
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
  startEdit(t:Task):void {this.editingId.set(t.id);this.editTitle=t.title;this.editNotes=t.notes;this.editDue=t.due??'';}
  cancelEdit():void {this.editingId.set(null);}
  async saveEdit(t:Task):Promise<void>{
    if(await this.store.update(t.id,{title:this.editTitle,notes:this.editNotes,due:this.editDue||null}))this.editingId.set(null);
  }
}

/** Today in the browser's time zone, as the tasks' due dates are plain calendar days. */
function localToday():string {
  const now=new Date();
  return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
