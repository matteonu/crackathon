import { Component, DestroyRef, ElementRef, computed, effect, forwardRef, inject, input, signal, viewChild } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { IconComponent } from './icon.component';

const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
const WEEKDAYS=['Mo','Tu','We','Th','Fr','Sa','Su'];
const iso=(y:number,m:number,d:number)=>`${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;

interface Day {date:string; day:number; outside:boolean; disabled:boolean;}

/** A calendar in the app's own style, for ISO dates (YYYY-MM-DD). It opens as a popover in the top layer,
 * so it floats over a dialog's other fields instead of growing the dialog. */
@Component({selector:'app-date-picker',standalone:true,imports:[IconComponent],
  providers:[{provide:NG_VALUE_ACCESSOR,useExisting:forwardRef(()=>DatePickerComponent),multi:true}],
  host:{'(document:click)':'outside($event)','(document:keydown.escape)':'escape($event)','(window:resize)':'place()'},template:`
  <button #field type="button" class="date-picker-field" [attr.aria-label]="label()" [attr.aria-expanded]="open()" [disabled]="disabled()" (click)="toggle()">
    <span [class.placeholder]="!value()">{{value()?display(value()):'Pick a date'}}</span><app-icon name="calendar" />
  </button>
    <div #panel class="date-picker-panel" popover="manual" role="group" [attr.aria-label]="label()">
      <div class="date-picker-head">
        <button type="button" class="icon-button" aria-label="Previous month" [disabled]="!canPrev()" (click)="shift(-1)"><app-icon name="left" /></button>
        <strong>{{monthName()}}</strong>
        <button type="button" class="icon-button" aria-label="Next month" [disabled]="!canNext()" (click)="shift(1)"><app-icon name="right" /></button>
      </div>
      <div class="date-picker-grid">
        @for(w of weekdays;track w){<span class="date-picker-weekday">{{w}}</span>}
        @for(d of days();track d.date){
          <button type="button" class="date-picker-day" [class.outside]="d.outside" [class.today]="d.date===today" [class.selected]="d.date===value()"
            [disabled]="d.disabled" [attr.aria-pressed]="d.date===value()" [attr.aria-label]="display(d.date)" (click)="pick(d.date)">{{d.day}}</button>
        }
      </div>
    </div>
`})
export class DatePickerComponent implements ControlValueAccessor {
  readonly min=input(''); readonly max=input(''); readonly label=input('Date');
  readonly value=signal(''); readonly open=signal(false); readonly disabled=signal(false);
  /** First of the month shown, as [year, month 0-11]. */
  readonly view=signal<[number,number]>([new Date().getFullYear(),new Date().getMonth()]);
  readonly weekdays=WEEKDAYS;
  readonly today=(()=>{const d=new Date();return iso(d.getFullYear(),d.getMonth(),d.getDate());})();
  private readonly host=inject(ElementRef<HTMLElement>);
  private readonly field=viewChild.required<ElementRef<HTMLElement>>('field');
  private readonly panel=viewChild.required<ElementRef<HTMLElement>>('panel');
  private onChange:(v:string)=>void=()=>{}; private onTouched:()=>void=()=>{};

  readonly monthName=computed(()=>`${MONTHS[this.view()[1]]} ${this.view()[0]}`);
  /** Whether the month before or after the shown one still has a pickable day. */
  readonly canPrev=computed(()=>{const [y,m]=this.view();return !this.min()||iso(y,m,1)>this.min();});
  readonly canNext=computed(()=>{const [y,m]=this.view();const d=new Date(y,m+1,1);return !this.max()||iso(d.getFullYear(),d.getMonth(),1)<=this.max();});
  readonly days=computed<Day[]>(()=>{
    const [y,m]=this.view();
    const lead=(new Date(y,m,1).getDay()+6)%7;
    const count=Math.ceil((lead+new Date(y,m+1,0).getDate())/7)*7;
    return Array.from({length:count},(_,i)=>{
      const d=new Date(y,m,1-lead+i);const date=iso(d.getFullYear(),d.getMonth(),d.getDate());
      return {date,day:d.getDate(),outside:d.getMonth()!==m,disabled:(!!this.min()&&date<this.min())||(!!this.max()&&date>this.max())};
    });
  });

  constructor(){
    effect(()=>{
      const panel=this.panel().nativeElement;
      if(this.open()){if(!panel.matches(':popover-open'))panel.showPopover();this.place();}
      else if(panel.matches(':popover-open'))panel.hidePopover();
    });
    // Scrolling the dialog moves the field, so the panel follows it. Scroll events don't bubble.
    const follow=()=>this.place();
    document.addEventListener('scroll',follow,true);
    inject(DestroyRef).onDestroy(()=>{document.removeEventListener('scroll',follow,true);if(this.panel().nativeElement.matches(':popover-open'))this.panel().nativeElement.hidePopover();});
  }

  /** Line the panel up under the field, or above it when there is no room below. */
  place():void {
    if(!this.open())return;
    const field=this.field().nativeElement.getBoundingClientRect();const panel=this.panel().nativeElement;
    const height=panel.offsetHeight;const below=field.bottom+6+height<=window.innerHeight-8;
    panel.style.left=`${field.left}px`;panel.style.width=`${field.width}px`;
    panel.style.top=`${below?field.bottom+6:Math.max(8,field.top-6-height)}px`;
  }
  display(date:string):string {const [y,m,d]=date.split('-');return `${Number(d)} ${MONTHS[Number(m)-1].slice(0,3)} ${y}`;}
  toggle():void {
    if(!this.open()){const anchor=this.value()||this.min()||this.today;this.view.set([Number(anchor.slice(0,4)),Number(anchor.slice(5,7))-1]);}
    this.open.update(o=>!o);
  }
  shift(by:number):void {this.view.update(([y,m])=>{const d=new Date(y,m+by,1);return [d.getFullYear(),d.getMonth()];});}
  pick(date:string):void {this.value.set(date);this.open.set(false);this.onChange(date);this.onTouched();}
  outside(event:Event):void {if(this.open()&&!this.host.nativeElement.contains(event.target as Node))this.open.set(false);}
  escape(event:Event):void {if(this.open()){event.preventDefault();event.stopPropagation();this.open.set(false);}}

  writeValue(value:string|null):void {this.value.set(value??'');this.open.set(false);}
  registerOnChange(fn:(v:string)=>void):void {this.onChange=fn;}
  registerOnTouched(fn:()=>void):void {this.onTouched=fn;}
  setDisabledState(disabled:boolean):void {this.disabled.set(disabled);}
}
