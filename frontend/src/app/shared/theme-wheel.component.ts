import { Component, ElementRef, HostListener, OnDestroy, computed, inject, signal, viewChild } from '@angular/core';
import { ThemeService } from '../services/theme.service';
import { THEMES, ThemeId, stepsToTheme, wheelMovement } from '../models/theme';

@Component({selector:'app-theme-wheel',standalone:true,template:`
  <button #trigger type="button" class="brand theme-trigger" aria-controls="theme-wheel" aria-describedby="theme-wheel-help"
    [attr.aria-expanded]="open()" [attr.aria-label]="'Theme: '+theme.current().label+'. Click for '+theme.next().label+', or scroll to spin the theme wheel.'"
    (pointerenter)="show()" (pointerleave)="scheduleHide()"
    (focus)="keyboardFocus()" (blur)="blur($event)" (click)="advance()" (wheel)="scroll($event)">
    <span #mark class="brand-mark">s<span>.</span></span><span #wordmark>studyphase</span>
  </button>
  <div #popover id="theme-wheel" class="theme-wheel" popover="manual" aria-label="Theme selection"
    (pointerenter)="cancelHide()" (pointerleave)="scheduleHide()" (focusin)="cancelHide()" (focusout)="blur($event)" (wheel)="scroll($event)">
    <div class="theme-orbit" role="group" aria-label="App theme" aria-describedby="theme-wheel-help">
      <div class="theme-track" [style.transform]="rotation()">
        @for(option of themes;track option.id;let i=$index){
          <div class="theme-spoke" [style.transform]="'rotate('+i*360/themes.length+'deg) translateX(var(--theme-radius))'">
            <div class="theme-reveal" [class.theme-reveal-current]="option.id===theme.current().id">
            <button type="button" class="theme-choice" [class.theme-choice-near]="nearby(option.id)"
              [attr.aria-current]="option.id===theme.current().id?'true':null" [attr.aria-hidden]="!nearby(option.id)"
              [attr.aria-label]="option.id===theme.current().id?'Current theme: '+option.label+'. Click for '+theme.next().label:'Switch to '+option.label"
              [attr.title]="option.label" [attr.data-theme]="option.id"
              [attr.tabindex]="option.id===theme.current().id?0:-1"
              (click)="choose(option.id)">
              <span class="theme-logo" aria-hidden="true">s<span>.</span></span>
            </button>
            </div>
          </div>
        }
      </div>
    </div>
    <span class="theme-label">{{theme.current().label}}</span>
    <span id="theme-wheel-help" class="sr-only">Click the current logo to advance one theme. Scroll or use arrow keys to switch. Escape closes the wheel.</span>
    <span class="sr-only" aria-live="polite" aria-atomic="true">{{theme.current().label}} theme selected</span>
  </div>
`,styles:`
  :host{display:block;flex-shrink:0;}
`})
export class ThemeWheelComponent implements OnDestroy {
  readonly theme=inject(ThemeService);
  readonly themes=THEMES;
  readonly open=signal(false);
  readonly rotation=computed(()=>`rotate(${-this.theme.step()*360/THEMES.length}deg)`);
  readonly trigger=viewChild.required<ElementRef<HTMLButtonElement>>('trigger');
  readonly mark=viewChild.required<ElementRef<HTMLSpanElement>>('mark');
  readonly wordmark=viewChild.required<ElementRef<HTMLSpanElement>>('wordmark');
  readonly popover=viewChild.required<ElementRef<HTMLDivElement>>('popover');
  private hideTimer?:ReturnType<typeof setTimeout>;
  private wheelRemainder=0;
  private lastWheel=0;
  private nextWheelAt=0;
  private suppressFocus=false;

  show():void {
    if(this.suppressFocus)return;
    this.cancelHide();
    if(this.open())return;
    this.popover().nativeElement.showPopover();
    this.open.set(true);
    this.position();
  }
  keyboardFocus():void{if(this.trigger().nativeElement.matches(':focus-visible'))this.show();}
  advance():void{this.show();this.theme.spin();}
  nearby(id:ThemeId):boolean{return Math.abs(stepsToTheme(this.theme.step(),id))<=1;}
  choose(id:ThemeId):void{this.theme.spin(id===this.theme.current().id?1:stepsToTheme(this.theme.step(),id));this.focusCurrent();}
  private focusCurrent():void {
    if(this.popover().nativeElement.contains(document.activeElement)){
      requestAnimationFrame(()=>this.popover().nativeElement.querySelector<HTMLButtonElement>('[aria-current="true"]')?.focus({preventScroll:true}));
    }
  }
  cancelHide():void{clearTimeout(this.hideTimer);}
  scheduleHide():void{
    this.cancelHide();
    this.hideTimer=setTimeout(()=>{
      const active=document.activeElement;
      if(active instanceof Element&&active.matches(':focus-visible')&&(this.trigger().nativeElement.contains(active)||this.popover().nativeElement.contains(active)))return;
      this.hide();
    },180);
  }
  blur(event:FocusEvent):void{
    const target=event.relatedTarget;
    if(target instanceof Node&&(this.trigger().nativeElement.contains(target)||this.popover().nativeElement.contains(target)))return;
    this.scheduleHide();
  }
  hide(returnFocus=false):void {
    this.cancelHide();
    if(!this.open())return;
    this.popover().nativeElement.hidePopover();this.open.set(false);
    this.wheelRemainder=0;this.nextWheelAt=0;
    if(returnFocus){this.suppressFocus=true;this.trigger().nativeElement.focus({preventScroll:true});this.suppressFocus=false;}
  }
  scroll(event:WheelEvent):void {
    if(event.ctrlKey)return;
    const delta=Math.abs(event.deltaY)>=Math.abs(event.deltaX)?event.deltaY:event.deltaX;
    if(!delta)return;
    event.preventDefault();event.stopPropagation();this.show();
    const now=performance.now();
    // Let one turn finish before accepting another; don't queue trackpad momentum.
    if(now<this.nextWheelAt){this.wheelRemainder=0;this.lastWheel=now;return;}
    if(now-this.lastWheel>180)this.wheelRemainder=0;
    this.lastWheel=now;
    const movement=wheelMovement(delta,event.deltaMode,this.wheelRemainder);
    this.wheelRemainder=movement.remainder;
    this.theme.spin(movement.steps);
    if(movement.steps){this.nextWheelAt=now+380;this.focusCurrent();}
  }
  @HostListener('keydown',['$event']) keys(event:KeyboardEvent):void {
    event.stopPropagation();
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();this.hide(true);return;}
    let steps=0;
    if(event.key==='ArrowRight'||event.key==='ArrowDown')steps=1;
    else if(event.key==='ArrowLeft'||event.key==='ArrowUp')steps=-1;
    else if(event.key==='Home')steps=stepsToTheme(this.theme.step(),'green');
    else if(event.key==='End')steps=stepsToTheme(this.theme.step(),'colorblind');
    else return;
    event.preventDefault();this.show();this.theme.spin(steps);
    this.focusCurrent();
  }
  @HostListener('document:pointerdown',['$event']) outside(event:PointerEvent):void {
    if(this.open()&&event.target instanceof Node&&!this.trigger().nativeElement.contains(event.target)&&!this.popover().nativeElement.contains(event.target))this.hide();
  }
  @HostListener('window:resize') position():void {
    if(!this.open())return;
    const mark=this.mark().nativeElement,anchor=mark.getBoundingClientRect();
    const label=this.wordmark().nativeElement.getBoundingClientRect(),panel=this.popover().nativeElement;
    const style=getComputedStyle(mark);
    panel.style.setProperty('--theme-logo-width',`${anchor.width}px`);
    panel.style.setProperty('--theme-logo-height',`${anchor.height}px`);
    panel.style.setProperty('--theme-logo-font',style.fontSize);
    panel.style.setProperty('--theme-logo-radius',style.borderRadius);
    panel.style.setProperty('--theme-logo-padding',style.paddingBottom);
    panel.style.setProperty('--theme-logo-spacing',style.letterSpacing);
    const radius=parseFloat(getComputedStyle(panel).getPropertyValue('--theme-radius'));
    // The rightmost tile lands exactly on the original logo, even near a viewport edge.
    const left=anchor.left+anchor.width/2-radius-panel.offsetWidth/2;
    const top=anchor.top+anchor.height/2-panel.offsetHeight/2;
    panel.style.left=`${left}px`;
    panel.style.top=`${top}px`;
    panel.style.setProperty('--theme-label-left',`${label.left-left}px`);
    panel.style.setProperty('--theme-label-top',`${label.bottom-top+4}px`);
  }
  @HostListener('window:scroll') closeOnScroll():void{if(this.open())this.hide();}
  ngOnDestroy():void{this.cancelHide();}
}
