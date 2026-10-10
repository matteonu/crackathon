import { Component, computed, inject, input, signal } from '@angular/core';
import { Material, ToolId } from '../models/material';
import { StudyDemoService } from '../services/study-demo.service';
import { MaterialStore } from '../services/material-store';

@Component({selector:'app-material-tool',standalone:true,template:`
  <section class="material-tool"><div class="tool-heading"><div><h3>{{title()}}</h3><p class="muted">{{description()}}</p></div><span class="demo-badge">Demo</span></div>
    <button class="button secondary" [disabled]="loading()" (click)="generate()">{{loading()?'Generating…':result()?'Regenerate '+title().toLowerCase():'Generate '+title().toLowerCase()}}</button>
    <div aria-live="polite">@if(error()){<p class="form-error">{{error()}} <button class="text-button" (click)="generate()">Retry</button></p>}
    @if(result();as output){
      @if(output.text){<p class="generated-text">{{output.text}}</p>}
      @for(card of output.cards;track $index){<details class="flashcard"><summary>{{card.question}}</summary><p>{{card.answer}}</p></details>}
    }</div>
  </section>
`})
export class MaterialToolComponent {
  readonly file=input.required<Material>();readonly tool=input.required<ToolId>();readonly title=input.required<string>();readonly description=input('');
  readonly loading=signal(false);readonly error=signal('');readonly result=computed(()=>this.file().outputs?.[this.tool()]??null);
  private readonly demo=inject(StudyDemoService);
  private readonly materials=inject(MaterialStore);
  async generate():Promise<void>{
    this.loading.set(true);this.error.set('');
    try{const result=await this.demo.generate(this.tool(),this.file());if(!await this.materials.update(this.file().id,{outputs:{[this.tool()]:result}}))throw new Error('Could not save result.');}
    catch{this.error.set('Generation failed. Try again.');}
    finally{this.loading.set(false);}
  }
}
