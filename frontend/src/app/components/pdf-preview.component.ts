import { Component, DestroyRef, ElementRef, computed, effect, inject, input, output, signal, viewChild } from '@angular/core';
import type { PDFDocumentProxy, PDFDocumentLoadingTask } from 'pdfjs-dist';
import { PdfPageComponent } from './pdf-page.component';
import { LoadingDotsComponent } from '../shared/loading-dots.component';
import { visiblePdfPage } from '../models/pdf-context';

@Component({selector:'app-pdf-preview',standalone:true,imports:[PdfPageComponent,LoadingDotsComponent],template:`
  <div class="pdf-reader">
    @if(error()){<p class="form-error" role="alert">{{error()}} You can still download the original file.</p>}
    @if(loading()){<p class="field-hint" role="status"><app-loading-dots label="Loading PDF" /></p>}
    <div #viewport class="pdf-pages" tabindex="0" role="region" aria-label="Scrollable PDF" (scroll)="trackPage()">
      @if(document();as pdf){
        @for(number of pages();track number){
          <app-pdf-page [attr.data-page]="number" [document]="pdf" [number]="number" [name]="name()" [initialAspect]="aspect()" [scrollRoot]="viewport" />
        }
      }
    </div>
  </div>
`})
export class PdfPreviewComponent {
  readonly url=input.required<string>();readonly name=input.required<string>();
  readonly initialPage=input(1);
  readonly pageChange=output<{page:number;total:number}>();
  private frame=0;
  readonly viewport=viewChild<ElementRef<HTMLElement>>('viewport');
  readonly document=signal<PDFDocumentProxy|null>(null);readonly loading=signal(true);readonly error=signal('');readonly aspect=signal(612/792);
  readonly pages=computed(()=>Array.from({length:this.document()?.numPages??0},(_,index)=>index+1));
  constructor(){
    inject(DestroyRef).onDestroy(()=>cancelAnimationFrame(this.frame));
    effect(onCleanup=>{
      const pdf=this.document(),viewport=this.viewport()?.nativeElement,page=this.initialPage();
      if(!pdf||!viewport)return;
      const target=Math.min(pdf.numPages,Math.max(1,Math.floor(page)||1));
      const frame=requestAnimationFrame(()=>{
        const element=viewport.querySelector<HTMLElement>(`[data-page="${target}"]`);
        if(element)viewport.scrollTop+=element.getBoundingClientRect().top-viewport.getBoundingClientRect().top;
        this.trackPage();
      });
      onCleanup(()=>cancelAnimationFrame(frame));
    });
    effect(onCleanup=>{
      const viewport=this.viewport()?.nativeElement;this.document();
      if(!viewport)return;
      const observer=new ResizeObserver(()=>this.trackPage());
      const frame=requestAnimationFrame(()=>{
        observer.observe(viewport);
        // Lazy rendering may change the height of individual portrait/landscape
        // pages without resizing the viewport itself.
        viewport.querySelectorAll('[data-page]').forEach(page=>observer.observe(page));
        this.trackPage();
      });
      onCleanup(()=>{cancelAnimationFrame(frame);observer.disconnect();});
    });
    effect(onCleanup=>{
      const url=this.url();let active=true;let task:PDFDocumentLoadingTask|undefined;
      this.loading.set(true);this.error.set('');this.document.set(null);this.pageChange.emit({page:0,total:0});
      void (async()=>{
        try{
          const pdf=await import('pdfjs-dist');if(!active)return;
          const assets=new URL('assets/pdfjs/',window.document.baseURI).href;
          pdf.GlobalWorkerOptions.workerSrc=assets+'pdf.worker.min.mjs?v='+pdf.version;
          task=pdf.getDocument({url,cMapUrl:assets+'cmaps/',cMapPacked:true,standardFontDataUrl:assets+'standard_fonts/',wasmUrl:assets+'wasm/'});
          const document=await task.promise;const first=await document.getPage(1);const size=first.getViewport({scale:1});
          if(active){this.aspect.set(size.width/size.height);this.document.set(document);const viewport=this.viewport()?.nativeElement;if(viewport)viewport.scrollTop=0;}
        }catch(e){if(active)console.warn('PDF preview failed:',e instanceof Error?e.message:'Unknown PDF error');if(active)this.error.set(e instanceof Error&&e.name==='PasswordException'?'Password-protected PDFs cannot be previewed.':'This PDF could not be previewed.');}
        finally{if(active)this.loading.set(false);}
      })();
      onCleanup(()=>{active=false;void task?.destroy();});
    });
  }
  trackPage():void {
    cancelAnimationFrame(this.frame);
    this.frame=requestAnimationFrame(()=>{
      const viewport=this.viewport()?.nativeElement;const total=this.document()?.numPages??0;
      if(!viewport||!total)return;
      const bounds=viewport.getBoundingClientRect();
      const positions=Array.from(viewport.querySelectorAll<HTMLElement>('[data-page]')).map(element=>{
        const rect=element.getBoundingClientRect();return {page:Number(element.dataset['page']),top:rect.top,bottom:rect.bottom};
      });
      const page=visiblePdfPage(positions,bounds.top,bounds.bottom);
      if(page)this.pageChange.emit({page,total});
    });
  }
}
