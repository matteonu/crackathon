import { Component, input } from '@angular/core';
import { IconComponent } from './icon.component';
@Component({selector:'app-scroll-buttons',standalone:true,imports:[IconComponent],template:`
  <div class="scroll-buttons"><button type="button" class="icon-button small" [attr.aria-label]="'Scroll '+label()+' left'" (click)="scroll(-1)"><app-icon name="left" /></button><button type="button" class="icon-button small" [attr.aria-label]="'Scroll '+label()+' right'" (click)="scroll(1)"><app-icon name="right" /></button></div>
`})
export class ScrollButtonsComponent {
  readonly target=input.required<HTMLElement>();readonly label=input('panel');
  scroll(direction:number):void {this.target().scrollBy({left:direction*this.target().clientWidth*.65,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
}
