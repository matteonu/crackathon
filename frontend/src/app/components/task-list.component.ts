import { Component, ElementRef, Injector, afterNextRender, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CdkDrag, CdkDragDrop, CdkDropList } from '@angular/cdk/drag-drop';
import { TaskStore } from '../services/task-store';
import { PRIORITIES, Priority, Task, MAX_TASK_NOTES, MAX_TASK_TITLE, doneTasks, dueLabel, dueState, openTasks } from '../models/task';
import { IconComponent } from '../shared/icon.component';

/** The subject's to-do list: add on Enter, tick off, click a row to edit, drag to reorder,
 *  clear completed. Dragging a task into another priority's group gives it
 *  that priority. */
@Component({selector:'app-task-list',standalone:true,imports:[FormsModule,IconComponent,CdkDropList,CdkDrag],template:`
  <section class="panel task-panel">
    <div class="panel-heading"><div><h2>To-do</h2><p>{{open().length}} open @if(done().length){· {{done().length}} done}</p></div></div>
    <form class="task-add" (ngSubmit)="add()">
      <label class="sr-only" for="task-title">New to-do</label>
      <input id="task-title" name="title" [(ngModel)]="draft" [maxlength]="maxTitle" placeholder="Add a to-do and press Enter" autocomplete="off" [disabled]="store.loading()">
      <label class="sr-only" for="task-priority">Priority</label>
      <select id="task-priority" class="task-priority-select" name="priority" [(ngModel)]="draftPriority" [disabled]="store.loading()">@for(p of priorities;track p.value){<option [value]="p.value">{{p.label}}</option>}</select>
      <button class="button primary" type="submit" [disabled]="!draft.trim()||store.loading()" aria-label="Add to-do"><app-icon name="plus" /></button>
    </form>
    @if(store.error()){<p class="form-error" role="alert">{{store.error()}}</p>}
    @if(store.loading()){<p class="muted task-empty">Loading your to-dos…</p>}
    <ul class="task-list" aria-label="Open to-dos" cdkDropList cdkDropListLockAxis="y" (cdkDropListDropped)="drop($event)">
      @for(t of open();track t.id){
        <li class="task" [class.task-editing]="editingId()===t.id" (click)="rowClick($event,t)" cdkDrag [cdkDragData]="t" [cdkDragDisabled]="editingId()===t.id" (cdkDragStarted)="dragged=true">
          <input type="checkbox" class="task-check" [checked]="t.done" (change)="store.toggle(t.id)" [attr.aria-label]="'Mark '+t.title+' as done'">
          @if(editingId()===t.id){
            <form class="task-edit task-fade" (ngSubmit)="saveEdit($event,t)">
              <label class="sr-only" for="edit-title">Title</label>
              <input #titleBox id="edit-title" name="title" [(ngModel)]="editTitle" [maxlength]="maxTitle" required (keydown.escape)="cancelEdit($event)">
              <label class="sr-only" for="edit-notes">Notes</label>
              <textarea id="edit-notes" name="notes" rows="2" [(ngModel)]="editNotes" [maxlength]="maxNotes" placeholder="Notes" (keydown.escape)="cancelEdit($event)"></textarea>
              <div class="task-edit-row">
                <div class="task-edit-fields"><label class="task-due-field">Due<input type="date" name="due" [(ngModel)]="editDue"></label>
                <label class="task-due-field">Priority<select name="priority" [(ngModel)]="editPriority">@for(p of priorities;track p.value){<option [value]="p.value">{{p.label}}</option>}</select></label></div>
                <div class="action-buttons"><button class="button primary" type="submit" [disabled]="!editTitle.trim()">Save</button><button class="text-button" type="button" (click)="cancelEdit($event)">Cancel</button></div>
              </div>
            </form>
          } @else {
            <div class="task-body task-fade">
              <span class="task-title">{{t.title}}</span>
              <div class="task-meta"><span [class]="'task-priority '+t.priority"><app-icon name="flag" />{{priorityLabel(t.priority)}}<span class="sr-only"> priority</span></span>
              @if(t.due){<span class="task-due" [class]="'task-due '+dueState(t.due,today())"><app-icon name="calendar" />{{dueLabel(t.due,today())}}</span>}</div>
            </div>
            <div class="task-tools">
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
                <div class="task-body"><span class="task-title">{{t.title}}</span></div>
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
  readonly maxTitle=MAX_TASK_TITLE;readonly maxNotes=MAX_TASK_NOTES;readonly dueState=dueState;readonly dueLabel=dueLabel;readonly priorities=PRIORITIES;
  readonly open=computed(()=>openTasks(this.store.tasks(),this.subjectId()));
  readonly done=computed(()=>doneTasks(this.store.tasks(),this.subjectId()));
  readonly today=signal(localToday());
  readonly editingId=signal<string|null>(null);readonly showDone=signal(false);
  private readonly titleField=viewChild<ElementRef<HTMLInputElement>>('titleBox');
  draft='';draftPriority:Priority='medium';editTitle='';editNotes='';editDue='';editPriority:Priority='medium';
  constructor(){
    effect(()=>{this.subjectId();this.editingId.set(null);this.draft='';this.draftPriority='medium';this.store.error.set('');});
    effect(()=>{const field=this.titleField();if(field&&this.editingId())field.nativeElement.focus();});
  }
  /** Set while a drag is under way and just after, so the click that ends a drag does not open the editor. */
  dragged=false;
  drop(event:CdkDragDrop<unknown,unknown,Task>):void {
    setTimeout(()=>this.dragged=false);
    void this.store.place(event.item.data.id,event.currentIndex);
  }
  async add():Promise<void>{
    const title=this.draft,priority=this.draftPriority;this.draft='';this.draftPriority='medium';this.today.set(localToday());
    if(!(await this.store.add(this.subjectId(),title,null,priority))){this.draft=title;this.draftPriority=priority;}
  }
  priorityLabel(priority:Priority):string {return PRIORITIES.find(p=>p.value===priority)?.label??priority;}
  /** Clicking anywhere on a row opens it, except on its own controls (checkbox, tools, the editor). */
  rowClick(event:Event,t:Task):void {
    if(this.dragged||this.editingId()===t.id||(event.target as HTMLElement).closest('input, button, textarea, label, form'))return;
    this.animateRow(event.currentTarget as HTMLElement,()=>{this.editingId.set(t.id);this.editTitle=t.title;this.editNotes=t.notes;this.editDue=t.due??'';this.editPriority=t.priority;});
  }
  cancelEdit(event:Event):void {this.animateRow(rowOf(event),()=>this.editingId.set(null));}
  async saveEdit(event:Event,t:Task):Promise<void>{
    const row=rowOf(event);
    if(await this.store.update(t.id,{title:this.editTitle,notes:this.editNotes,due:this.editDue||null,priority:this.editPriority}))this.animateRow(row,()=>this.editingId.set(null));
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
