import { Component, computed, inject } from '@angular/core';
import { StudyStore } from '../services/study-store';
import { CALENDAR_HOURS, calendarViewport, courseEventColumns } from '../models/calendar';
import { minutesOf } from '../models/semester';
import { CalendarScrollDirective } from '../shared/calendar-scroll.directive';
import { CalendarNowComponent } from '../shared/calendar-now.component';

@Component({selector: 'app-today-calendar', standalone: true,
  imports: [CalendarScrollDirective, CalendarNowComponent],
  template: `
    @if(allDay().length){<div class="today-all-day">@for(entry of allDay();track entry.id){
      <div [style.--event-color]="entry.color"><span>All day · {{entry.label}}</span><strong>{{entry.name}}</strong></div>
    }</div>}
    <div class="today-calendar-scroll" tabindex="0" role="region" aria-label="Today's calendar, midnight to 23:59"
      [calendarScrollStart]="store.loaded() ? viewport().offset : null">
      <div class="today-calendar-grid" [style.height.px]="viewport().fullHeight" [style.--hour-height]="hourHeight() + 'px'">
        <div class="today-time-axis">@for(hour of hours;track hour){
          <span [style.top.px]="hour * hourHeight()">{{hour.toString().padStart(2,'0')}}:00</span>
        }<span class="day-end">23:59</span></div>
        <div class="today-events">
          @for(entry of timed();track entry.id){
            <div class="today-calendar-event" [class.is-short]="entry.height < 42" [style.--event-color]="entry.color"
              [style.top.px]="entry.top" [style.height.px]="entry.height" [style.left.%]="entry.column / entry.columns * 100"
              [style.width.%]="100 / entry.columns" role="img" [attr.aria-label]="entry.description" [title]="entry.description">
              <strong>{{entry.name}}</strong><span>{{entry.start}}–{{entry.end}} · {{entry.label}}</span>
            </div>
          }
          <app-calendar-now [style.top.px]="store.clock().minutes / 60 * hourHeight()" />
        </div>
      </div>
    </div>
  `,
  styles: `
    :host { display:block; margin-top:18px; }
    .today-calendar-scroll { height:354px; overflow-y:auto; overscroll-behavior:contain; scrollbar-width:thin; border:1px solid var(--line); border-radius:8px; }
    .today-calendar-grid { display:grid; grid-template-columns:44px minmax(0,1fr); }
    .today-time-axis, .today-events { position:relative; }
    .today-time-axis > span { position:absolute; left:5px; padding-top:2px; font-size:9px; color:var(--muted); font-variant-numeric:tabular-nums; }
    .today-time-axis > .day-end { bottom:1px; }
    .today-events { border-left:1px solid var(--line); background:repeating-linear-gradient(to bottom,var(--line) 0,var(--line) 1px,transparent 1px,transparent var(--hour-height)); }
    .today-calendar-event { position:absolute; border-left:3px solid var(--event-color); border-right:3px solid var(--surface); border-radius:4px; padding:4px 6px; background:color-mix(in srgb,var(--event-color) 12%,var(--surface)); overflow:hidden; }
    .today-calendar-event strong { display:block; font-size:10px; font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .today-calendar-event > span { display:block; font-size:9px; color:var(--muted); white-space:nowrap; margin-top:3px; }
    .today-calendar-event.is-short { padding-top:1px; padding-bottom:0; }
    .today-calendar-event.is-short > span { display:none; }
    .today-all-day { display:grid; gap:5px; margin-bottom:8px; }
    .today-all-day > div { border-left:3px solid var(--event-color); padding:5px 8px; background:var(--surface-soft); border-radius:4px; }
    .today-all-day span, .today-all-day strong { display:block; font-size:10px; font-weight:400; }
    .today-all-day span { color:var(--muted); margin-bottom:3px; }
  `})
export class TodayCalendarComponent {
  readonly store = inject(StudyStore);
  readonly hours = CALENDAR_HOURS;
  // Fit the user's entire preferred range in the compact overview panel.
  readonly hourHeight = computed(() => {
    const range = calendarViewport(this.store.preferences().dayStart, this.store.preferences().dayEnd, 60);
    return 352 / ((range.end - range.start) / 60);
  });
  readonly viewport = computed(() => calendarViewport(this.store.preferences().dayStart, this.store.preferences().dayEnd, this.hourHeight()));
  readonly allDay = computed(() => this.store.todayPlan().filter(entry => !entry.start || !entry.end));
  readonly timed = computed(() => courseEventColumns(this.store.todayPlan().flatMap(entry =>
    entry.start && entry.end ? [{...entry, start: entry.start, end: entry.end}] : [])).map(entry => ({...entry,
      top: minutesOf(entry.start) / 60 * this.hourHeight(),
      height: Math.max(1, (minutesOf(entry.end) - minutesOf(entry.start)) / 60 * this.hourHeight() - 2),
      description: `${entry.name}, ${entry.label}, ${entry.start}–${entry.end}`,
    })));
}
