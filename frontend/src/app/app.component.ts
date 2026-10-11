import { Component, DestroyRef, ElementRef, HostListener, inject, signal, viewChild } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { installPopupDismissal } from './models/popup-dismissal';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, NavigationEnd, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { StudyStore } from './services/study-store';
import { UserStore } from './services/user-store';
import { IconComponent } from './shared/icon.component';
import { HoursEditorComponent } from './shared/hours-editor.component';
import { CourseSearchDialogComponent } from './components/course-search-dialog.component';
import { Subject } from './models/study';
import { semesterName } from './models/semester';
import { ThemeWheelComponent } from './shared/theme-wheel.component';

@Component({selector:'app-root',standalone:true,imports:[RouterLink,RouterLinkActive,RouterOutlet,IconComponent,HoursEditorComponent,CourseSearchDialogComponent,ThemeWheelComponent],templateUrl:'./app.component.html'})
export class AppComponent {
  readonly store=inject(StudyStore);readonly users=inject(UserStore);private readonly router=inject(Router);
  readonly main=viewChild<ElementRef<HTMLElement>>('main');
  readonly settings=viewChild<ElementRef<HTMLDialogElement>>('settings');
  private pageMotion:Animation|null=null;
  private previousPage=this.router.url;
  constructor(){
    const destroyRef=inject(DestroyRef);
    destroyRef.onDestroy(installPopupDismissal(inject(DOCUMENT)));
    destroyRef.onDestroy(()=>this.pageMotion?.cancel());
    this.router.events.pipe(filter(e=>e instanceof NavigationEnd),takeUntilDestroyed()).subscribe(event=>{
      const subjectRoute=(url:string)=>/^\/subject-tab\/[^/?#;]+(?:[?#;].*)?$/.test(url);
      const betweenSubjects=subjectRoute(this.previousPage)&&subjectRoute(event.urlAfterRedirects);
      this.previousPage=event.urlAfterRedirects;
      requestAnimationFrame(()=>{
        const main=this.main()?.nativeElement;
        main?.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});
        this.pageMotion?.cancel();this.pageMotion=null;
        if(!betweenSubjects&&main?.animate&&!matchMedia('(prefers-reduced-motion: reduce)').matches){
          this.pageMotion=main.animate([{transform:'translateY(4px)'},{transform:'translateY(0)'}],{duration:160,easing:'ease-out'});
        }
      });
    });
  }
  /** The sidebar course whose ⋯ menu is open. */
  readonly menuFor=signal<string|null>(null);
  toggleMenu(id:string,event:Event):void {
    event.stopPropagation();
    this.semesterMenu.set(false);this.profileMenu.set(false);
    const opening=this.menuFor()!==id;this.menuFor.set(opening?id:null);
    // Move focus into the menu so it can be used from the keyboard.
    if(opening)requestAnimationFrame(()=>document.querySelector<HTMLElement>('.course-menu [role=menuitem]')?.focus());
  }
  @HostListener('document:click') closeMenu():void {this.menuFor.set(null);this.semesterMenu.set(false);this.profileMenu.set(false);}
  @HostListener('document:keydown.escape') closeMenuOnEscape():void {
    if(this.profileMenu()){this.profileMenu.set(false);document.querySelector<HTMLElement>('.profile-button')?.focus();return;}
    if(this.semesterMenu()){this.semesterMenu.set(false);document.querySelector<HTMLElement>('.semester-switch')?.focus();return;}
    const id=this.menuFor();if(!id)return;
    this.menuFor.set(null);
    document.querySelector<HTMLElement>(`.sidebar-subject a[href$="${id}"] + .course-menu-button`)?.focus();
  }
  /** The account menu behind the profile at the bottom of the sidebar. */
  readonly profileMenu=signal(false);
  toggleProfileMenu(event:Event):void {
    event.stopPropagation();this.menuFor.set(null);this.semesterMenu.set(false);
    const opening=!this.profileMenu();this.profileMenu.set(opening);
    if(opening)requestAnimationFrame(()=>document.querySelector<HTMLElement>('.profile-menu [role=menuitem]')?.focus());
  }
  /** The semester picker at the bottom of the sidebar. */
  readonly semesterMenu=signal(false);
  readonly semesterName=semesterName;
  toggleSemesterMenu(event:Event):void {
    event.stopPropagation();this.menuFor.set(null);this.profileMenu.set(false);
    const opening=!this.semesterMenu();this.semesterMenu.set(opening);
    if(opening)requestAnimationFrame(()=>document.querySelector<HTMLElement>('.semester-menu [aria-checked=true]')?.focus());
  }
  async chooseSemester(semkez:string):Promise<void> {
    this.semesterMenu.set(false);
    await this.store.selectSemester(semkez);
    // A subject page of a course the new semester doesn't have would say "Subject not found".
    const open=/^\/subject-tab\/(.+)$/.exec(this.router.url)?.[1];
    if(open&&!this.store.subjects().some(s=>s.id===open))void this.router.navigate(['/']);
  }
  openSettings():void {this.settings()?.nativeElement.showModal();}
  async removeCourse(subject:Subject):Promise<void> {
    if(!confirm(`Remove ${subject.name} from ${this.store.data().semester}? Its recorded hours and planned sessions are deleted too. Your materials stay and come back if you add the course again.`))return;
    const viewing=this.router.url===`/subject-tab/${subject.id}`;
    try{await this.store.removeCourse(subject);if(viewing)void this.router.navigate(['/']);}
    catch(e){this.store.announce(e instanceof Error?e.message:'Could not remove this course.');}
  }
}
