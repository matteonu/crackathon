import { Component, ElementRef, inject, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, NavigationEnd, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { StudyStore } from './services/study-store';
import { UserStore } from './services/user-store';
import { IconComponent } from './shared/icon.component';
import { HoursEditorComponent } from './shared/hours-editor.component';
import { CourseSearchDialogComponent } from './components/course-search-dialog.component';
import { Subject } from './models/study';

@Component({selector:'app-root',standalone:true,imports:[RouterLink,RouterLinkActive,RouterOutlet,IconComponent,HoursEditorComponent,CourseSearchDialogComponent],templateUrl:'./app.component.html'})
export class AppComponent {
  readonly store=inject(StudyStore);readonly users=inject(UserStore);private readonly router=inject(Router);
  readonly main=viewChild<ElementRef<HTMLElement>>('main');
  readonly settings=viewChild<ElementRef<HTMLDialogElement>>('settings');
  constructor(){this.router.events.pipe(filter(e=>e instanceof NavigationEnd),takeUntilDestroyed()).subscribe(()=>{requestAnimationFrame(()=>{this.main()?.nativeElement.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});});});}
  openSettings():void {this.settings()?.nativeElement.showModal();}
  async removeCourse(subject:Subject):Promise<void> {
    if(!confirm(`Remove ${subject.name} from ${this.store.data().semester}? Its recorded hours and planned sessions are deleted too. Your materials stay and come back if you add the course again.`))return;
    const viewing=this.router.url===`/subject-tab/${subject.id}`;
    try{await this.store.removeCourse(subject);if(viewing)void this.router.navigate(['/']);}
    catch(e){this.store.announce(e instanceof Error?e.message:'Could not remove this course.');}
  }
}
