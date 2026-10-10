import { Component, input } from '@angular/core';

@Component({
  selector: 'app-loading-dots', standalone: true,
  template: `<span class="loading-label">{{label()}}<span class="loading-dots" aria-hidden="true">.<span>.</span><span>.</span></span></span>`,
  styles: `
    :host { display:inline; }
    .loading-label { white-space:normal; }
    .loading-dots { display:inline-flex; width:1.1em; text-align:left; }
    .loading-dots span { opacity:0; animation:loading-dot-two 1.5s step-end infinite; }
    .loading-dots span:last-child { animation-name:loading-dot-three; }
    @keyframes loading-dot-two { 0%,100%{opacity:0} 33.333%{opacity:1} }
    @keyframes loading-dot-three { 0%,100%{opacity:0} 66.667%{opacity:1} }
    @media(prefers-reduced-motion:reduce){.loading-dots span{animation:none;opacity:1}}
  `,
})
export class LoadingDotsComponent { readonly label=input('Loading'); }
