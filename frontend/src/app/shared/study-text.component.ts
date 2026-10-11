import { ChangeDetectionStrategy, Component, ElementRef, computed, effect, inject, input, viewChild } from '@angular/core';
import { splitStudyText } from '../models/study-text';
import { StudyMathService } from '../services/study-math.service';

@Component({selector:'app-study-math',standalone:true,changeDetection:ChangeDetectionStrategy.OnPush,
  template:'<span #equation class="study-equation" [class.display-equation]="display()"></span>',
  styles:':host{display:inline;max-width:100%;}'})
export class StudyMathComponent {
  readonly latex=input.required<string>();readonly source=input.required<string>();readonly display=input(false);
  readonly equation=viewChild<ElementRef<HTMLSpanElement>>('equation');
  private readonly math=inject(StudyMathService);
  constructor(){
    effect(onCleanup=>{
      const element=this.equation()?.nativeElement,latex=this.latex(),source=this.source(),display=this.display();if(!element)return;
      let active=true;element.textContent=source;
      const stop=this.math.whenVisible(element,()=>{
        void this.math.render(latex,display).then(html=>{
          if(!active||html===null)return;
          // Only KaTeX-produced HTML enters this element; raw text is always
          // assigned via textContent, with trust disabled and expansion bounded.
          element.innerHTML=html;
        });
      });
      onCleanup(()=>{active=false;stop();});
    });
  }
}

@Component({selector:'app-study-text',standalone:true,imports:[StudyMathComponent],changeDetection:ChangeDetectionStrategy.OnPush,
  template:`@for(part of parts();track $index){@if(part.kind==='math'){<app-study-math [latex]="part.latex" [source]="part.source" [display]="part.display&&!compact()" />}@else{<span>{{part.text}}</span>}}`,
  styles:':host{display:inline;white-space:pre-wrap;overflow-wrap:anywhere;max-width:100%;}'})
export class StudyTextComponent {
  readonly text=input.required<string>();readonly compact=input(false);
  readonly parts=computed(()=>splitStudyText(this.text()));
}
