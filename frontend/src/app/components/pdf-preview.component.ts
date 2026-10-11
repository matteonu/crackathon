import { Component, DestroyRef, ElementRef, computed, effect, inject, input, output, signal, untracked, viewChild } from '@angular/core';
import type { PDFDocumentProxy, PDFDocumentLoadingTask } from 'pdfjs-dist';
import { PdfPageComponent } from './pdf-page.component';
import { LoadingDotsComponent } from '../shared/loading-dots.component';
import { visiblePdfPage } from '../models/pdf-context';
import { createPdfPageCache } from '../models/pdf-render';

@Component({selector:'app-pdf-preview',standalone:true,imports:[PdfPageComponent,LoadingDotsComponent],template:`
  <div class="pdf-reader">
    @if(error()){<p class="form-error" role="alert">{{error()}} You can still download the original file.</p>}
    @if(loading()){<p class="field-hint" role="status"><app-loading-dots label="Loading PDF" /></p>}
    <div #viewport class="pdf-pages" tabindex="0" role="region" aria-label="Scrollable PDF">
      @if(document();as pdf){
        @for(number of pages();track number){
          <div class="pdf-page-slot" [attr.data-page]="number">
            <div class="pdf-page-label">Page {{number}} of {{pdf.numPages}}</div>
            <div class="pdf-page-frame" [style.aspect-ratio]="pageAspects().get(number)??aspect()">
              @if(nearbyPages().has(number)){
                @if(renderWidth()>0){<app-pdf-page [document]="pdf" [number]="number" [name]="name()" [displayWidth]="renderWidth()" [cache]="pageCache()" (aspectChange)="rememberAspect(number,$event)" />}
              }@else{<p class="pdf-page-placeholder">Page {{number}}</p>}
            </div>
          </div>
        }
      }
    </div>
  </div>
`,styles:`
  .pdf-page-slot{position:relative;margin:0 auto 20px;max-width:100%;}
  .pdf-page-label{font-size:10px;color:var(--muted);padding:5px 0 8px;}
  .pdf-page-frame{position:relative;background:white;box-shadow:0 1px 5px #00000018;overflow:hidden;}
  .pdf-page-placeholder{padding:24px;text-align:center;font-size:12px;}
`})
export class PdfPreviewComponent {
  readonly url=input.required<string>();readonly name=input.required<string>();
  readonly initialPage=input(1);
  readonly pageChange=output<{page:number;total:number}>();
  private frame=0;
  private readonly visiblePages=new Set<HTMLElement>();
  private lastContext:{page:number;total:number}|null=null;
  readonly viewport=viewChild<ElementRef<HTMLElement>>('viewport');
  readonly document=signal<PDFDocumentProxy|null>(null);readonly loading=signal(true);readonly error=signal('');readonly aspect=signal(612/792);
  readonly pages=computed(()=>Array.from({length:this.document()?.numPages??0},(_,index)=>index+1));
  readonly nearbyPages=signal<ReadonlySet<number>>(new Set());
  readonly pageAspects=signal<ReadonlyMap<number,number>>(new Map());
  readonly renderWidth=signal(0);
  readonly pageCache=signal(createPdfPageCache());
  constructor(){
    inject(DestroyRef).onDestroy(()=>{cancelAnimationFrame(this.frame);this.pageCache().close();});
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
      const viewport=this.viewport()?.nativeElement,pdf=this.document();
      if(!viewport||!pdf)return;
      let active=true;
      const onScroll=()=>this.trackPage();
      // Native scrolling doesn't ask Angular to check the viewer every frame.
      viewport.addEventListener('scroll',onScroll,{passive:true});
      const updateWidth=()=>{
        const style=getComputedStyle(viewport);
        const width=Math.round(viewport.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight));
        if(width>0)this.renderWidth.set(width);
      };
      const observer=new ResizeObserver(entries=>{
        if(!active)return;
        if(entries.some(entry=>entry.target===viewport))updateWidth();
        this.trackPage();
      });
      const visibility=new IntersectionObserver(entries=>{
        if(!active)return;
        for(const entry of entries){
          const page=entry.target as HTMLElement;
          if(entry.isIntersecting)this.visiblePages.add(page);else this.visiblePages.delete(page);
        }
        this.trackPage();
      },{root:viewport});
      // One shared observer mounts renderers only in the buffered viewport.
      const rendering=new IntersectionObserver(entries=>{
        if(!active)return;
        const next=new Set(this.nearbyPages());let changed=false;
        for(const entry of entries){
          const page=Number((entry.target as HTMLElement).dataset['page']);
          if(entry.isIntersecting&&!next.has(page)){next.add(page);changed=true;}
          else if(!entry.isIntersecting&&next.delete(page))changed=true;
        }
        if(changed)this.nearbyPages.set(next);
      },{root:viewport,rootMargin:'800px 0px'});
      const frame=requestAnimationFrame(()=>{
        updateWidth();
        observer.observe(viewport);
        // Lazy rendering may change the height of individual portrait/landscape
        // pages without resizing the viewport itself.
        viewport.querySelectorAll('[data-page]').forEach(page=>{
          observer.observe(page);visibility.observe(page);rendering.observe(page);
        });
        this.trackPage();
      });
      onCleanup(()=>{
        active=false;cancelAnimationFrame(frame);cancelAnimationFrame(this.frame);this.frame=0;
        viewport.removeEventListener('scroll',onScroll);
        observer.disconnect();visibility.disconnect();rendering.disconnect();this.visiblePages.clear();
      });
    });
    effect(onCleanup=>{
      const url=this.url();let active=true;let task:PDFDocumentLoadingTask|undefined;
      this.loading.set(true);this.error.set('');this.document.set(null);this.emitPageContext(0,0);
      this.nearbyPages.set(new Set());this.pageAspects.set(new Map());
      untracked(()=>this.pageCache().close());this.pageCache.set(createPdfPageCache());
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
  rememberAspect(page:number,aspect:number):void{
    if(this.pageAspects().get(page)===aspect)return;
    // Retain each page's dimensions when its renderer is unmounted, so mixed
    // portrait/landscape documents don't change scroll height on the return trip.
    this.pageAspects.update(current=>new Map(current).set(page,aspect));
  }
  trackPage():void {
    if(this.frame)return;
    this.frame=requestAnimationFrame(()=>{
      this.frame=0;
      const viewport=this.viewport()?.nativeElement;const total=this.document()?.numPages??0;
      if(!viewport||!total)return;
      const bounds=viewport.getBoundingClientRect();
      const positions=Array.from(this.visiblePages).map(element=>{
        const rect=element.getBoundingClientRect();return {page:Number(element.dataset['page']),top:rect.top,bottom:rect.bottom};
      }).sort((a,b)=>a.page-b.page);
      const page=visiblePdfPage(positions,bounds.top,bounds.bottom);
      if(page)this.emitPageContext(page,total);
    });
  }
  private emitPageContext(page:number,total:number):void{
    if(this.lastContext?.page===page&&this.lastContext.total===total)return;
    this.lastContext={page,total};this.pageChange.emit(this.lastContext);
  }
}
