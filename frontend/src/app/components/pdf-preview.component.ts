import { Component, ElementRef, effect, input, signal, viewChild } from '@angular/core';
import type { PDFDocumentProxy, PDFDocumentLoadingTask, RenderTask } from 'pdfjs-dist';

@Component({selector:'app-pdf-preview',standalone:true,template:`
  <div class="pdf-reader"><div class="pdf-toolbar"><button class="icon-button" aria-label="Previous PDF page" [disabled]="page()<=1||loading()" (click)="page.update(previous)">‹</button><span aria-live="polite">Page {{page()}} of {{document()?.numPages??'…'}}</span><button class="icon-button" aria-label="Next PDF page" [disabled]="page()>=(document()?.numPages??1)||loading()" (click)="page.update(next)">›</button></div>
    @if(error()){<p class="form-error" role="alert">{{error()}} You can still download the original below.</p>}
    @if(loading()){<p class="field-hint" role="status">Loading PDF…</p>}
    <div class="pdf-canvas-wrap"><canvas #canvas [hidden]="!document()||!!error()" role="img" [attr.aria-label]="'Page '+page()+' of '+name()"></canvas></div>
    <p class="sr-only">{{pageText()}}</p>
  </div>
`})
export class PdfPreviewComponent {
  readonly blob=input.required<Blob>();readonly name=input.required<string>();
  readonly canvas=viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  readonly document=signal<PDFDocumentProxy|null>(null);readonly page=signal(1);readonly loading=signal(true);readonly error=signal('');readonly pageText=signal('');
  readonly previous=(page:number)=>page-1;readonly next=(page:number)=>page+1;
  constructor(){
    effect(onCleanup=>{
      const blob=this.blob();let active=true;let task:PDFDocumentLoadingTask|undefined;
      this.loading.set(true);this.error.set('');this.document.set(null);this.page.set(1);
      void (async()=>{
        try{
          const pdf=await import('pdfjs-dist');const data=await blob.arrayBuffer();if(!active)return;
          const assets=new URL('assets/pdfjs/',window.document.baseURI).href;
          pdf.GlobalWorkerOptions.workerSrc=assets+'pdf.worker.min.mjs';
          task=pdf.getDocument({data,cMapUrl:assets+'cmaps/',cMapPacked:true,standardFontDataUrl:assets+'standard_fonts/',wasmUrl:assets+'wasm/'});
          const document=await task.promise;if(active)this.document.set(document);
        }catch(e){if(active){this.error.set(e instanceof Error&&e.name==='PasswordException'?'Password-protected PDFs cannot be previewed.':'This PDF could not be previewed.');this.loading.set(false);}}
      })();
      onCleanup(()=>{active=false;void task?.destroy();});
    });
    effect(onCleanup=>{
      const document=this.document();const number=this.page();const canvas=this.canvas()?.nativeElement;if(!document||!canvas)return;
      let active=true;let render:RenderTask|undefined;this.loading.set(true);this.pageText.set('');
      void (async()=>{
        try{
          const page=await document.getPage(number);if(!active)return;
          const viewport=page.getViewport({scale:1.5});canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
          render=page.render({canvas,viewport});await render.promise;
          const text=await page.getTextContent();if(active)this.pageText.set(text.items.map(item=>'str' in item?item.str:'').join(' '));
        }catch(e){if(active&&!(e instanceof Error&&e.name==='RenderingCancelledException'))this.error.set('This page could not be rendered.');}
        finally{if(active)this.loading.set(false);}
      })();
      onCleanup(()=>{active=false;render?.cancel();});
    });
  }
}

