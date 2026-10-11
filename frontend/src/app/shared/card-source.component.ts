import { Component, input } from '@angular/core';
import { Flashcard, sourcePageUrl } from '../models/material';

/** One citation presentation for card lists, previews and learning sessions. */
@Component({selector:'app-card-source',standalone:true,template:`
  @if(card().source;as source){
    <span>Source: </span>
    @for(page of source.pages;track page){
      @if(!$first){<span> · </span>}
      @if(source.pdfId){
        <a [href]="pageUrl(source.pdfId,page)" target="_blank" rel="noopener noreferrer"
           [attr.aria-label]="'Source: '+source.pdfName+' page '+page+' (opens in a new tab)'"
           (click)="$event.stopPropagation()" (keydown)="$event.stopPropagation()">{{source.pdfName}} page {{page}}</a>
      }@else{<span>{{source.pdfName}} page {{page}}</span>}
    }
    @if(!source.pdfId){<span> (PDF deleted)</span>}
  }@else if(card().generated){<span>Source not recorded</span>}
`,styles:`
  :host{display:block;color:var(--muted);font-size:11px;font-weight:400;line-height:1.5;overflow-wrap:anywhere;text-align:inherit;}
  :host:empty{display:none;}
  a{color:inherit;text-decoration:underline;text-decoration-color:var(--line-strong);text-underline-offset:3px;}
  a:hover,a:focus-visible{color:var(--accent);text-decoration-color:currentColor;}
`})
export class CardSourceComponent {
  readonly card=input.required<Flashcard>();
  readonly pageUrl=sourcePageUrl;
}
