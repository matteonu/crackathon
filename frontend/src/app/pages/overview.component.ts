import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { TaskStore } from '../services/task-store';
import { MaterialStore } from '../services/material-store';
import { IconComponent } from '../shared/icon.component';
import { Material, MaterialMarker, materialKind, materialTypeLabel } from '../models/material';
import { MAX_TASK_TITLE, PRIORITIES, Priority, Task, dueLabel, dueState } from '../models/task';
import { MATERIAL_STATES, OVERVIEW_QUOTES, materialCoverage, overviewMaterials, overviewTasks } from '../models/overview';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink, IconComponent],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.css',
})
export class OverviewComponent {
  readonly store = inject(StudyStore);
  readonly tasks = inject(TaskStore);
  readonly materials = inject(MaterialStore);
  readonly quote = OVERVIEW_QUOTES[Math.floor(Math.random() * OVERVIEW_QUOTES.length)];
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
  readonly boardCourse = signal('');
  readonly filteredFiles = computed(() => this.files().filter(file => !this.boardCourse() || file.subjectId === this.boardCourse()));
  readonly columns = computed(() => this.states.map(state => ({...state, files: this.filteredFiles().filter(file => file.marker === state.marker)})));
  readonly ready = computed(() => this.store.loaded() && !this.materials.loading());
  readonly showDone = signal(false);
  readonly expandedStates = signal(new Set<MaterialMarker>());
  readonly pendingTasks = signal(new Set<string>());
  readonly pendingFiles = signal(new Set<string>());
  readonly adding = signal(false);
  readonly notice = signal('');
  readonly draftCourse = signal('');
  draftTitle = '';
  draftPriority: Priority = 'medium';

  constructor() {
    effect(() => {
      const ids = this.subjectIds();
      if (!ids.has(this.draftCourse())) this.draftCourse.set(this.store.subjects()[0]?.id ?? '');
      if (this.boardCourse() && !ids.has(this.boardCourse())) this.boardCourse.set('');
    });
  }

  subjectName(id: string): string { return this.subjectsById().get(id)?.name ?? ''; }
  private today(): string {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
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

  async updateTask(task: Task, patch: {done?: boolean; priority?: Priority}): Promise<void> {
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

  toggleState(marker: MaterialMarker): void {
    this.expandedStates.update(ids => { const next = new Set(ids); next.has(marker) ? next.delete(marker) : next.add(marker); return next; });
  }
}

