import { Component, input, output } from '@angular/core';
import type { LearningMode } from '../models/material';

@Component({
  selector:'app-learning-mode', standalone:true,
  template:`<div class="learning-mode-control">
    <span class="learning-mode-label">{{label()}}</span>
    <div class="learning-mode-options" role="group" [attr.aria-label]="label()">
      <button type="button" [class.selected]="mode()==='shallow'" [attr.aria-pressed]="mode()==='shallow'" [disabled]="disabled()" (click)="modeChange.emit('shallow')">Shallow</button>
      <button type="button" [class.selected]="mode()==='deep'" [attr.aria-pressed]="mode()==='deep'" [disabled]="disabled()" (click)="modeChange.emit('deep')">Deep</button>
    </div>
    <span class="learning-mode-hint">{{mode()==='deep'?'Text, images, charts and diagrams · Slower':'Extracted text only · Faster'}}</span>
  </div>`,
})
export class LearningModeComponent {
  readonly label=input('Processing mode');readonly mode=input<LearningMode>('shallow');readonly disabled=input(false);
  readonly modeChange=output<LearningMode>();
}
