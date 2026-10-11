import { DOCUMENT, Injectable, computed, inject, signal } from '@angular/core';
import { THEMES, THEME_STORAGE_KEY, ThemeId, themeId, themeIndex } from '../models/theme';

@Injectable({providedIn:'root'})
export class ThemeService {
  private readonly document=inject(DOCUMENT);
  readonly step=signal(this.initialStep());
  readonly current=computed(()=>THEMES[themeIndex(this.step())]);
  readonly next=computed(()=>THEMES[themeIndex(this.step()+1)]);

  constructor(){this.apply(this.current().id);}

  spin(steps=1):void {
    if(!Number.isFinite(steps)||!Number.isInteger(steps)||!steps)return;
    this.step.update(value=>value+steps);
    this.apply(this.current().id);
  }

  private initialStep():number {
    let id:ThemeId='green';
    try{id=themeId(this.document.defaultView?.localStorage.getItem(THEME_STORAGE_KEY));}catch{/* Storage may be disabled. */}
    return THEMES.findIndex(theme=>theme.id===id);
  }

  private apply(id:ThemeId):void {
    this.document.documentElement.dataset['theme']=id;
    const color=getComputedStyle(this.document.documentElement).getPropertyValue('--canvas').trim();
    this.document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content',color);
    try{this.document.defaultView?.localStorage.setItem(THEME_STORAGE_KEY,id);}catch{/* Theme changes still work without storage. */}
  }
}
