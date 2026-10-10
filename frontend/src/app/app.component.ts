import { Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, NavigationEnd, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { StudyStore } from './services/study-store';
import { UserStore } from './services/user-store';
import { IconComponent } from './shared/icon.component';
import { HoursEditorComponent } from './shared/hours-editor.component';

@Component({selector:'app-root',standalone:true,imports:[RouterLink,RouterLinkActive,RouterOutlet,IconComponent,HoursEditorComponent],templateUrl:'./app.component.html'})
export class AppComponent {
  readonly store=inject(StudyStore);readonly users=inject(UserStore);private readonly router=inject(Router);
  readonly main=viewChild<ElementRef<HTMLElement>>('main');
  readonly settings=viewChild<ElementRef<HTMLDialogElement>>('settings');
  readonly importError=signal('');
  constructor(){this.router.events.pipe(filter(e=>e instanceof NavigationEnd),takeUntilDestroyed()).subscribe(()=>{requestAnimationFrame(()=>{this.main()?.nativeElement.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});});});}
  openSettings():void {this.importError.set('');this.settings()?.nativeElement.showModal();}
  reset():void {if(confirm('Restore the original HS24 sample? This replaces the changes saved in this browser. Export first if you want to keep a copy.')){this.store.reset();this.settings()?.nativeElement.close();void this.router.navigate(['/']);}}
  async import(event:Event):Promise<void> {
    const input=event.target as HTMLInputElement;const file=input.files?.[0];if(!file)return;
    try {if(file.size>1024*1024)throw new Error('Choose a data file smaller than 1 MB.');this.store.importData(JSON.parse(await file.text()));this.importError.set('');this.settings()?.nativeElement.close();void this.router.navigate(['/']);}
    catch(e){this.importError.set(e instanceof SyntaxError?'This is not a valid JSON file.':(e as Error).message);}
    finally{input.value='';}
  }
}
