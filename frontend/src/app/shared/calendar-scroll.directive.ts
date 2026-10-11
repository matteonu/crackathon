import { Directive, ElementRef, afterRenderEffect, inject, input } from '@angular/core';

/** Apply the preferred start after layout. Ordinary clock/event updates preserve manual scrolling. */
@Directive({selector: '[calendarScrollStart]', standalone: true})
export class CalendarScrollDirective {
  readonly calendarScrollStart = input.required<number | null>();
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  constructor() {
    afterRenderEffect({write: () => {
      const offset = this.calendarScrollStart();
      if (offset !== null) this.element.nativeElement.scrollTop = offset;
    }});
  }
}
