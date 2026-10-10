import { Component, ElementRef, effect, inject, input, signal, viewChild } from '@angular/core';
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';
import { LoadingDotsComponent } from '../shared/loading-dots.component';

/** Keep the full document scrollable while limiting canvas memory to nearby pages. */
@Component({selector:'app-pdf-page',standalone:true,imports:[LoadingDotsComponent],template:`
  <div class="pdf-page-label">Page {{number()}} of {{document().numPages}}</div>
  <div class="pdf-page" [style.aspect-ratio]="aspect()??initialAspect()">
    <canvas #canvas [hidden]="!ready()" role="img" [attr.aria-label]="'Page '+number()+' of '+name()"></canvas>
    @if(error()){<p class="form-error" role="alert">{{error()}}</p>}
    @else if(!ready()){<p class="pdf-page-placeholder">@if(nearby()){<app-loading-dots label="Loading page" />}@else{Page {{number()}}}</p>}
  </div>
  <p class="sr-only">{{text()}}</p>
`,styles:`
  /* Anchor the hidden text to its page so it cannot extend the enclosing dialog. */
  :host{display:block;position:relative;margin:0 auto 20px;max-width:100%;}
  .sr-only{top:0;left:0;margin:0;}
  .pdf-page-label{font-size:10px;color:var(--muted);padding:5px 0 8px;}
  .pdf-page{position:relative;background:white;box-shadow:0 1px 5px #00000018;overflow:hidden;}
  canvas{display:block;width:100%;height:100%;position:absolute;inset:0;}
  canvas[hidden]{display:none;}
  .pdf-page-placeholder,.form-error{padding:24px;text-align:center;font-size:12px;}
`})
export class PdfPageComponent {
  readonly document=input.required<PDFDocumentProxy>();readonly number=input.required<number>();readonly name=input.required<string>();
  readonly scrollRoot=input.required<HTMLElement>();readonly initialAspect=input.required<number>();
  readonly canvas=viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  readonly nearby=signal(false);readonly ready=signal(false);readonly aspect=signal<number|null>(null);readonly text=signal('');readonly error=signal('');
  private readonly host=inject(ElementRef<HTMLElement>);
  constructor(){
    effect(onCleanup=>{
      const observer=new IntersectionObserver(entries=>this.nearby.set(entries.some(entry=>entry.isIntersecting)),{root:this.scrollRoot(),rootMargin:'800px 0px'});
      observer.observe(this.host.nativeElement);onCleanup(()=>observer.disconnect());
    });
    effect(onCleanup=>{
      const document=this.document();const number=this.number();const nearby=this.nearby();const canvas=this.canvas()?.nativeElement;if(!canvas)return;
      this.ready.set(false);if(!nearby){canvas.width=1;canvas.height=1;return;}
      let active=true;let render:RenderTask|undefined;this.error.set('');
      void (async()=>{
        try{
          const page=await document.getPage(number);if(!active)return;
          const viewport=page.getViewport({scale:1.5});this.aspect.set(viewport.width/viewport.height);
          canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
          render=page.render({canvas,viewport});await render.promise;if(!active)return;this.ready.set(true);
          const text=await page.getTextContent();if(active)this.text.set(text.items.map(item=>'str' in item?item.str:'').join(' '));
        }catch(e){if(active&&!(e instanceof Error&&e.name==='RenderingCancelledException'))this.error.set(`Page ${number} could not be rendered.`);}
      })();
      onCleanup(()=>{active=false;render?.cancel();});
    });
  }
}
