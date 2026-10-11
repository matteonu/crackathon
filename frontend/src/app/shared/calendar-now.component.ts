import { Component, inject } from '@angular/core';
import { StudyStore } from '../services/study-store';

@Component({selector: 'app-calendar-now', standalone: true,
  host: {'role': 'img', '[attr.aria-label]': "'Current time: ' + store.clock().label"},
  template: `<span>{{store.clock().label}}</span>`,
  styles: `
    :host { position:absolute; left:0; right:0; z-index:6; border-top:2px solid var(--danger); pointer-events:none; }
    :host::before { content:''; position:absolute; width:7px; height:7px; border-radius:50%; background:var(--danger); left:-4px; top:-4.5px; }
    span { position:absolute; left:5px; bottom:3px; padding:1px 4px; border-radius:3px; background:var(--surface); color:var(--danger); font-size:10px; font-weight:600; font-variant-numeric:tabular-nums; }
  `})
export class CalendarNowComponent { readonly store = inject(StudyStore); }
