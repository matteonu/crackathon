import { Component, ElementRef, effect, input, output, signal, viewChild } from '@angular/core';
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';
import { LoadingDotsComponent } from '../shared/loading-dots.component';
import { CachedPdfPage, PdfPageCache, pdfRenderScale } from '../models/pdf-render';

/** A renderer mounted only while its page is near the viewport. */
@Component({selector:'app-pdf-page',standalone:true,imports:[LoadingDotsComponent],template:`
  <div class="pdf-page">
    <canvas #canvas [hidden]="!ready()" role="img" [attr.aria-label]="'Page '+number()+' of '+name()"></canvas>
    @if(error()){<p class="form-error" role="alert">{{error()}}</p>}
    @else if(!ready()){<p class="pdf-page-placeholder"><app-loading-dots label="Loading page" /></p>}
  </div>
  <p class="sr-only">{{text()}}</p>
`,styles:`
  /* Anchor the hidden text to its page so it cannot extend the enclosing dialog. */
  :host{display:block;position:absolute;inset:0;}
  .sr-only{top:0;left:0;margin:0;}
  .pdf-page{position:absolute;inset:0;overflow:hidden;}
  canvas{display:block;width:100%;height:100%;position:absolute;inset:0;}
  canvas[hidden]{display:none;}
  .pdf-page-placeholder,.form-error{padding:24px;text-align:center;font-size:12px;}
`})
export class PdfPageComponent {
  readonly document=input.required<PDFDocumentProxy>();readonly number=input.required<number>();readonly name=input.required<string>();
  readonly displayWidth=input.required<number>();readonly cache=input.required<PdfPageCache<CachedPdfPage>>();
  readonly aspectChange=output<number>();
  readonly canvas=viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  readonly ready=signal(false);readonly text=signal('');readonly error=signal('');
  constructor(){
    effect(onCleanup=>{
      const document=this.document(),number=this.number(),width=this.displayWidth(),cache=this.cache();
      const canvas=this.canvas()?.nativeElement;if(!canvas)return;
      const pixelRatio=Math.min(2,Math.max(1,window.devicePixelRatio||1)),key=`${number}:${width}:${pixelRatio}`;
      this.ready.set(false);this.text.set('');
      let active=true,rendered=false,aspect=1,extractedText:string|null=null;let render:RenderTask|undefined;this.error.set('');
      void (async()=>{
        try{
          const cached=cache.take(key);
          if(cached){
            canvas.width=cached.canvas.width;canvas.height=cached.canvas.height;
            const context=canvas.getContext('2d');
            if(context){context.drawImage(cached.canvas,0,0);rendered=true;aspect=cached.aspect;extractedText=cached.text;this.aspectChange.emit(aspect);this.ready.set(true);this.text.set(extractedText??'');}
            cached.canvas.width=1;cached.canvas.height=1;
            if(rendered&&extractedText!==null)return;
          }
          const page=await document.getPage(number);if(!active)return;
          if(!rendered){
            const size=page.getViewport({scale:1});aspect=size.width/size.height;this.aspectChange.emit(aspect);
            const viewport=page.getViewport({scale:pdfRenderScale(size.width,size.height,width,pixelRatio)});
            canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
            render=page.render({canvas,viewport});await render.promise;if(!active)return;rendered=true;this.ready.set(true);
          }
          const text=await page.getTextContent();if(active){extractedText=text.items.map(item=>'str' in item?item.str:'').join(' ');this.text.set(extractedText);}
        }catch(e){if(active&&!(e instanceof Error&&e.name==='RenderingCancelledException'))this.error.set(`Page ${number} could not be rendered.`);}
      })();
      onCleanup(()=>{
        active=false;render?.cancel();
        if(rendered&&!cache.isClosed){
          const copy=window.document.createElement('canvas');copy.width=canvas.width;copy.height=canvas.height;
          const context=copy.getContext('2d');
          if(context){context.drawImage(canvas,0,0);cache.put(key,{canvas:copy,pixels:copy.width*copy.height,text:extractedText,aspect});}
        }
        canvas.width=1;canvas.height=1;
      });
    });
  }
}
