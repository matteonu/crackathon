import { Component, ElementRef, HostListener, OnDestroy, computed, inject, signal, viewChild } from '@angular/core';
import { ThemeService } from '../services/theme.service';
import { THEMES, ThemeId, stepsToTheme, wheelMovement } from '../models/theme';

@Component({selector:'app-theme-wheel',standalone:true,template:`
  <button #trigger type="button" class="brand theme-trigger" aria-controls="theme-wheel" aria-describedby="theme-wheel-help"
    [attr.aria-expanded]="open()" [attr.aria-label]="'Theme: '+theme.current().label+'. Click for '+theme.next().label+', or scroll to spin the theme wheel.'"
    (pointerenter)="hover()" (pointerleave)="scheduleHide()" (pointerdown)="cancelHover()"
    (focus)="keyboardFocus()" (blur)="blur($event)" (click)="advance()" (wheel)="scroll($event)">
    <span class="brand-mark">s<span>.</span></span><span>studyphase</span>
  </button>
  <div #popover id="theme-wheel" class="theme-wheel" popover="manual" aria-label="Theme selection"
    (pointerenter)="cancelHide()" (pointerleave)="scheduleHide()" (focusin)="cancelHide()" (focusout)="blur($event)" (wheel)="scroll($event)">
    <button type="button" class="theme-close" aria-label="Close theme wheel" (click)="hide(true)">×</button>
    <div class="theme-orbit" role="group" aria-label="App theme" aria-describedby="theme-wheel-help">
      <div class="theme-track" [style.transform]="rotation()">
        @for(option of themes;track option.id;let i=$index){
          <div class="theme-spoke" [style.transform]="'rotate('+i*360/themes.length+'deg) translateX(var(--theme-radius))'">
            <button type="button" class="theme-choice" [class.theme-choice-near]="nearby(option.id)"
              [attr.aria-current]="option.id===theme.current().id?'true':null" [attr.aria-hidden]="!nearby(option.id)"
              [attr.aria-label]="option.id===theme.current().id?'Current theme: '+option.label+'. Click for '+theme.next().label:'Switch to '+option.label"
              [attr.title]="option.label" [attr.data-theme]="option.id"
              [attr.tabindex]="option.id===theme.current().id?0:-1"
              (click)="choose(option.id)">
              <span class="theme-logo" aria-hidden="true">s<span>.</span></span>
            </button>
          </div>
        }
      </div>
    </div>
    <button type="button" class="theme-wordmark" [attr.aria-label]="'Next theme: '+theme.next().label" (click)="advance()">
      <strong>studyphase</strong><span>{{theme.current().label}} · {{currentPosition()}} / {{themes.length}}</span>
    </button>
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
  readonly currentPosition=computed(()=>THEMES.findIndex(t=>t.id===this.theme.current().id)+1);
  readonly trigger=viewChild.required<ElementRef<HTMLButtonElement>>('trigger');
  readonly popover=viewChild.required<ElementRef<HTMLDivElement>>('popover');
  private hideTimer?:ReturnType<typeof setTimeout>;
  private hoverTimer?:ReturnType<typeof setTimeout>;
  private wheelRemainder=0;
  private lastWheel=0;
  private nextWheelAt=0;
  private suppressFocus=false;

  show():void {
    if(this.suppressFocus)return;
    this.cancelHide();this.cancelHover();
    if(this.open())return;
    this.popover().nativeElement.showPopover();
    this.open.set(true);
    this.position();
  }
  hover():void {
    this.cancelHide();this.cancelHover();
    // A quick click must reach the original logo before the expanded arc moves it.
    if(!this.open())this.hoverTimer=setTimeout(()=>this.show(),200);
  }
  cancelHover():void{clearTimeout(this.hoverTimer);}
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
    this.cancelHide();this.cancelHover();
    this.hideTimer=setTimeout(()=>{
      const active=document.activeElement;
      if(active&&(this.trigger().nativeElement.contains(active)||this.popover().nativeElement.contains(active)))return;
      this.hide();
    },180);
  }
  blur(event:FocusEvent):void{
    const target=event.relatedTarget;
    if(target instanceof Node&&(this.trigger().nativeElement.contains(target)||this.popover().nativeElement.contains(target)))return;
    this.scheduleHide();
  }
  hide(returnFocus=false):void {
    this.cancelHide();this.cancelHover();
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
    const anchor=this.trigger().nativeElement.getBoundingClientRect(),panel=this.popover().nativeElement;
    panel.style.left=`${Math.max(8,Math.min(anchor.left+anchor.height/2-94,innerWidth-panel.offsetWidth-8))}px`;
    panel.style.top=`${Math.max(8,Math.min(anchor.top+anchor.height/2-panel.offsetHeight/2,innerHeight-panel.offsetHeight-8))}px`;
  }
  @HostListener('window:scroll') closeOnScroll():void{if(this.open())this.hide();}
  ngOnDestroy():void{this.cancelHide();this.cancelHover();}
}
