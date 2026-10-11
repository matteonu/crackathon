import { Component, DestroyRef, ElementRef, computed, effect, inject, signal } from '@angular/core';
import { CdkDrag, CdkDragDrop, CdkDropList, CdkDropListGroup } from '@angular/cdk/drag-drop';
import { CdkScrollable } from '@angular/cdk/scrolling';
import { CdkMenu, CdkMenuItemRadio, CdkMenuTrigger } from '@angular/cdk/menu';
import type { ConnectedPosition } from '@angular/cdk/overlay';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { TaskStore } from '../services/task-store';
import { MaterialStore } from '../services/material-store';
import { UserStore } from '../services/user-store';
import { IconComponent } from '../shared/icon.component';
import { Material, MaterialMarker, materialKind, materialTypeLabel } from '../models/material';
import { MAX_TASK_TITLE, PRIORITIES, Priority, Task, dueLabel, dueState } from '../models/task';
import { MATERIAL_STATES, OVERVIEW_GREETINGS, localDateKey, materialCoverage, overviewDayPlan, overviewMaterials, overviewTasks } from '../models/overview';
import { dayLabel } from '../models/study';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink, IconComponent, CdkDrag, CdkDropList, CdkDropListGroup, CdkScrollable, CdkMenu, CdkMenuItemRadio, CdkMenuTrigger],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.css',
})
export class OverviewComponent {
  readonly store = inject(StudyStore);
  readonly tasks = inject(TaskStore);
  readonly materials = inject(MaterialStore);
  private readonly users = inject(UserStore);
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly greetingTemplate = OVERVIEW_GREETINGS[Math.floor(Math.random() * OVERVIEW_GREETINGS.length)];
  readonly greeting = computed(() => {
    const user = this.users.user();
    return user ? this.greetingTemplate.replace('USERNAME', () => user.name.trim() || user.email) : '';
  });
  readonly priorities = PRIORITIES;
  readonly states = MATERIAL_STATES;
  readonly maxTitle = MAX_TASK_TITLE;
  readonly kind = materialKind;
  readonly typeLabel = materialTypeLabel;
  readonly subjectIds = computed(() => new Set(this.store.subjects().map(subject => subject.id)));
  readonly subjectsById = computed(() => new Map(this.store.subjects().map(subject => [subject.id, subject])));
  readonly openTasks = computed(() => overviewTasks(this.tasks.tasks(), this.subjectIds()));
  readonly completedTasks = computed(() => this.tasks.tasks().filter(task => this.subjectIds().has(task.subjectId) && task.done)
    .sort((a, b) => (b.completedAt ?? 0) - (a.completedAt ?? 0)));
  readonly files = computed(() => overviewMaterials(this.materials.files(), this.subjectIds()));
  readonly coverage = computed(() => materialCoverage(this.files()));
  readonly courseProgress = computed(() => this.store.subjects().map(subject => ({subject,
    ...materialCoverage(this.files().filter(file => file.subjectId === subject.id))})));
  readonly today = signal(localDateKey(new Date()));
  readonly todayLabel = computed(() => dayLabel(this.today(), {weekday: 'long', day: 'numeric', month: 'long'}));
  readonly todayPlan = computed(() => overviewDayPlan(this.store.generatedPlan()?.blocks ?? [], this.store.subjects(), this.today()));
  readonly boardCourse = signal('');
  readonly boardCourseLabel = computed(() => this.subjectsById().get(this.boardCourse())?.name ?? 'All courses');
  readonly courseFilterPositions: ConnectedPosition[] = [
    {originX: 'end', originY: 'bottom', overlayX: 'end', overlayY: 'top', offsetY: 6},
    {originX: 'end', originY: 'top', overlayX: 'end', overlayY: 'bottom', offsetY: -6},
  ];
  readonly filteredFiles = computed(() => this.files().filter(file => !this.boardCourse() || file.subjectId === this.boardCourse()));
  readonly columns = computed(() => this.states.map(state => ({...state, files: this.filteredFiles().filter(file => file.marker === state.marker)})));
  readonly ready = computed(() => this.store.loaded() && !this.materials.loading());
  readonly showDone = signal(false);
  readonly pendingTasks = signal(new Set<string>());
  readonly pendingFiles = signal(new Set<string>());
  readonly adding = signal(false);
  readonly notice = signal('');
  readonly draftCourse = signal('');
  draftTitle = '';
  draftPriority: Priority = 'medium';

  constructor() {
    // Keep the day current even when the overview stays open overnight.
    const dayTimer = setInterval(() => this.today.set(localDateKey(new Date())), 60_000);
    inject(DestroyRef).onDestroy(() => clearInterval(dayTimer));
    effect(() => {
      const ids = this.subjectIds();
      if (!ids.has(this.draftCourse())) this.draftCourse.set(this.store.subjects()[0]?.id ?? '');
      if (this.boardCourse() && !ids.has(this.boardCourse())) this.boardCourse.set('');
    });
  }

  subjectName(id: string): string { return this.subjectsById().get(id)?.name ?? ''; }
  priorityLabel(priority: Priority): string { return this.priorities.find(item => item.value === priority)!.label; }
  overdue(task: Task): boolean { return !!task.due && dueState(task.due, this.today()) === 'overdue'; }
  dueText(task: Task): string { return task.due ? `${this.overdue(task) ? 'Overdue · ' : ''}${dueLabel(task.due, this.today())}` : ''; }

  async addTask(): Promise<void> {
    if (!this.draftTitle.trim() || !this.subjectIds().has(this.draftCourse()) || this.adding()) return;
    this.adding.set(true);
    try {
      const saved = await this.tasks.add(this.draftCourse(), this.draftTitle, null, this.draftPriority);
      if (saved) { this.draftTitle = ''; this.notice.set('To-do added.'); }
    } finally { this.adding.set(false); }
  }

  async updateTask(task: Task, patch: {done: boolean}): Promise<void> {
    if (this.pendingTasks().has(task.id)) return;
    this.pendingTasks.update(ids => new Set(ids).add(task.id));
    try {
      if (await this.tasks.update(task.id, patch)) this.notice.set(patch.done === true ? 'To-do completed.' : 'To-do updated.');
    } finally { this.pendingTasks.update(ids => { const next = new Set(ids); next.delete(task.id); return next; }); }
  }

  async setMarker(file: Material, marker: MaterialMarker): Promise<void> {
    if (this.pendingFiles().has(file.id) || file.marker === marker) return;
    this.pendingFiles.update(ids => new Set(ids).add(file.id));
    try {
      if (await this.materials.update(file.id, {marker})) this.notice.set(`${file.name} moved to ${marker}.`);
    } finally { this.pendingFiles.update(ids => { const next = new Set(ids); next.delete(file.id); return next; }); }
  }

  dropMaterial(event: CdkDragDrop<MaterialMarker, MaterialMarker, Material>): void {
    if (event.isPointerOverContainer) void this.setMarker(event.item.data, event.container.data);
  }

  async moveMaterialWithKeyboard(event: KeyboardEvent, file: Material): Promise<void> {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const index = this.states.findIndex(state => state.marker === file.marker);
    const target = this.states[index + (event.key === 'ArrowRight' ? 1 : -1)];
    if (!target || this.pendingFiles().has(file.id)) return;
    await this.setMarker(file, target.marker);
    // The card moves between lists, so restore keyboard focus after Angular renders it.
    setTimeout(() => {
      const buttons = this.element.nativeElement.querySelectorAll<HTMLButtonElement>('[data-move-file]');
      Array.from(buttons).find(button => button.dataset['moveFile'] === file.id)?.focus();
    });
  }
}

