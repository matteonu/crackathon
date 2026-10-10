import { Component, ElementRef, computed, effect, input, signal, viewChild } from '@angular/core';
import type { PDFDocumentProxy, PDFDocumentLoadingTask } from 'pdfjs-dist';
import { PdfPageComponent } from './pdf-page.component';
import { LoadingDotsComponent } from '../shared/loading-dots.component';

@Component({selector:'app-pdf-preview',standalone:true,imports:[PdfPageComponent,LoadingDotsComponent],template:`
  <div class="pdf-reader">
    @if(error()){<p class="form-error" role="alert">{{error()}} You can still download the original file.</p>}
    @if(loading()){<p class="field-hint" role="status"><app-loading-dots label="Loading PDF" /></p>}
    <div #viewport class="pdf-pages" tabindex="0" role="region" aria-label="Scrollable PDF">
      @if(document();as pdf){
        @for(number of pages();track number){
          <app-pdf-page [document]="pdf" [number]="number" [name]="name()" [initialAspect]="aspect()" [scrollRoot]="viewport" />
        }
      }
    </div>
  </div>
`})
export class PdfPreviewComponent {
  readonly blob=input.required<Blob>();readonly name=input.required<string>();
  readonly viewport=viewChild<ElementRef<HTMLElement>>('viewport');
  readonly document=signal<PDFDocumentProxy|null>(null);readonly loading=signal(true);readonly error=signal('');readonly aspect=signal(612/792);
  readonly pages=computed(()=>Array.from({length:this.document()?.numPages??0},(_,index)=>index+1));
  constructor(){
    effect(onCleanup=>{
      const blob=this.blob();let active=true;let task:PDFDocumentLoadingTask|undefined;
      this.loading.set(true);this.error.set('');this.document.set(null);
      void (async()=>{
        try{
          const pdf=await import('pdfjs-dist');const data=await blob.arrayBuffer();if(!active)return;
          const assets=new URL('assets/pdfjs/',window.document.baseURI).href;
          pdf.GlobalWorkerOptions.workerSrc=assets+'pdf.worker.min.mjs';
          task=pdf.getDocument({data,cMapUrl:assets+'cmaps/',cMapPacked:true,standardFontDataUrl:assets+'standard_fonts/',wasmUrl:assets+'wasm/'});
          const document=await task.promise;const first=await document.getPage(1);const size=first.getViewport({scale:1});
          if(active){this.aspect.set(size.width/size.height);this.document.set(document);const viewport=this.viewport()?.nativeElement;if(viewport)viewport.scrollTop=0;}
        }catch(e){if(active)this.error.set(e instanceof Error&&e.name==='PasswordException'?'Password-protected PDFs cannot be previewed.':'This PDF could not be previewed.');}
        finally{if(active)this.loading.set(false);}
      })();
      onCleanup(()=>{active=false;void task?.destroy();});
    });
  }
}
