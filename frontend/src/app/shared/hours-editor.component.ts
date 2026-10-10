import { Component, ElementRef, effect, inject, signal, untracked, viewChild } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { StudyStore } from '../services/study-store';
import { IconComponent } from './icon.component';
import { segmentedDate } from '../models/study';

@Component({selector:'app-hours-editor',standalone:true,imports:[ReactiveFormsModule,IconComponent],template:`
  <dialog #dialog class="edit-dialog" aria-labelledby="hours-heading" (close)="store.editor.set(null)" (cancel)="store.editor.set(null)">
    <form [formGroup]="form" (ngSubmit)="save()">
      <div class="dialog-top"><span class="eyebrow">MAKE IT COUNT</span><button type="button" class="icon-button" aria-label="Close editor" (click)="dialog.close()"><app-icon name="close" /></button></div>
      <h2 id="hours-heading">Record study time</h2>
      <p class="muted">Set the total recorded hours for one subject on one day.</p>
      <label>Subject<select formControlName="subject">@for(s of store.subjects();track s.id){<option [value]="s.id">{{s.name}}</option>}</select></label>
      <fieldset class="date-fieldset"><legend>Date</legend><div class="segmented-date">
        <input aria-label="Day" placeholder="DD" inputmode="numeric" maxlength="2" formControlName="day"><span>/</span>
        <input aria-label="Month" placeholder="MM" inputmode="numeric" maxlength="2" formControlName="month"><span>/</span>
        <input aria-label="Year" placeholder="YYYY" inputmode="numeric" maxlength="4" formControlName="year">
      </div><p class="field-hint">Exam session: {{displayDate(store.examSession().start)}} – {{displayDate(store.examSession().end)}}</p>
      @if(dateError()){<p class="form-error" role="alert">{{dateError()}}</p>}</fieldset>
      <label>Hours<input #hoursInput type="number" formControlName="hours" min="0" max="24" step="0.25" required placeholder="e.g. 2.5"></label>
      <p class="field-hint">Saving replaces this day's value. Clearing means no record; 0 means zero hours recorded.</p>
      @if(error()){<p class="form-error" role="alert">{{error()}}</p>}
      <div class="dialog-actions"><button type="button" class="text-button" [disabled]="!!dateError()" (click)="commit(null)">Clear entry</button><button class="button primary" type="submit" [disabled]="!!dateError()">Save hours <app-icon name="check" /></button></div>
    </form>
  </dialog>
`})
export class HoursEditorComponent {
  readonly store=inject(StudyStore);
  readonly dialog=viewChild<ElementRef<HTMLDialogElement>>('dialog');
  readonly hoursInput=viewChild<ElementRef<HTMLInputElement>>('hoursInput');
  readonly error=signal(''); readonly dateError=signal('');
  readonly form=new FormGroup({subject:new FormControl('',{nonNullable:true}),day:new FormControl('',{nonNullable:true}),month:new FormControl('',{nonNullable:true}),year:new FormControl('',{nonNullable:true}),hours:new FormControl<number|null>(null)});
  readonly displayDate=(date:string)=>date.split('-').reverse().join('/');
  constructor(){
    for(const control of [this.form.controls.subject,this.form.controls.day,this.form.controls.month,this.form.controls.year]){
      control.valueChanges.pipe(takeUntilDestroyed()).subscribe(()=>this.readExisting());
    }
    effect(()=>{
      const request=this.store.editor();const dialog=this.dialog()?.nativeElement;
      if(!dialog)return;
      untracked(()=>{
        if(request){
          const [year,month,day]=request.date.split('-');
          // Reactive controls write to the input synchronously, before the dialog receives focus.
          this.form.reset({subject:request.subjectId,day,month,year,hours:null},{emitEvent:false});
          this.readExisting();
          if(!dialog.open)dialog.showModal();
          this.hoursInput()?.nativeElement.focus();
        } else if(dialog.open)dialog.close();
      });
    });
  }
  private date():string|null {
    const v=this.form.getRawValue();return segmentedDate(v.day,v.month,v.year);
  }
  readExisting():void {
    const date=this.date();
    const valid=date && date>=this.store.examSession().start && date<=this.store.examSession().end && this.store.dates().includes(date);
    this.dateError.set(!date?'Enter a complete, valid date as DD/MM/YYYY.':!valid?'Choose a date within the exam session.':'');
    const subject=this.store.subjects().find(s=>s.id===this.form.controls.subject.value);
    const planned=valid?this.store.planHoursFor(this.form.controls.subject.value,[date]):0;
    this.form.controls.hours.setValue(valid?(planned>0?planned:subject?.hours[date]??null):null,{emitEvent:false});
    this.error.set('');
  }
  save():void {const hours=this.form.controls.hours.value;if(hours===null){this.error.set('Enter hours, or use Clear entry.');return;}this.commit(hours);}
  commit(value:number|null):void {
    if(this.dateError())return;
    try{this.store.setHours(this.form.controls.subject.value,this.date()!,value);}catch(e){this.error.set((e as Error).message);}
  }
}
