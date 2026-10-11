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
    const palette=getComputedStyle(this.document.documentElement);
    this.document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content',palette.getPropertyValue('--canvas').trim());
    const background=palette.getPropertyValue('--accent').trim();
    const foreground=palette.getPropertyValue('--on-accent').trim();
    const icon=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="13" fill="${background}"/><path d="M31 14H21a6 6 0 0 0 0 12h6a4 4 0 0 1 0 8H16" fill="none" stroke="${foreground}" stroke-width="4" stroke-linecap="round"/></svg>`;
    this.document.querySelector<HTMLLinkElement>('link[rel="icon"]')?.setAttribute('href',`data:image/svg+xml,${encodeURIComponent(icon)}`);
    try{this.document.defaultView?.localStorage.setItem(THEME_STORAGE_KEY,id);}catch{/* Theme changes still work without storage. */}
  }
}
