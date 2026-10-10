import { Component, computed, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { MaterialStore } from '../services/material-store';
import { materialFileUrl } from '../models/material';
import { PdfPreviewComponent } from '../components/pdf-preview.component';

@Component({selector:'app-pdf-source',standalone:true,imports:[PdfPreviewComponent],template:`
  @if(file();as file){
    <section class="pdf-source-view">
      <header><h1>{{file.name}}</h1><a [href]="fileUrl()" download>Download PDF</a></header>
      <app-pdf-preview [url]="fileUrl()" [name]="file.name" [initialPage]="page()" />
    </section>
  }@else if(materials.loading()){<p role="status">Loading source PDF…</p>}
  @else{<p role="alert">{{materials.error()||'This source PDF is no longer available.'}}</p>}
`,styles:`
  .pdf-source-view{padding:24px;}
  header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:18px;}
  h1{font-size:22px;overflow-wrap:anywhere;margin:0;}
  a{font-size:12px;white-space:nowrap;color:var(--muted);}
`})
export class PdfSourceComponent {
  readonly materials=inject(MaterialStore);
  private readonly route=inject(ActivatedRoute);
  private readonly params=toSignal(this.route.paramMap,{initialValue:this.route.snapshot.paramMap});
  private readonly query=toSignal(this.route.queryParamMap,{initialValue:this.route.snapshot.queryParamMap});
  readonly file=computed(()=>this.materials.files().find(f=>f.id===this.params().get('id')&&f.kind==='pdf'));
  readonly fileUrl=computed(()=>materialFileUrl(this.file()!.id));
  readonly page=computed(()=>{const value=Number(this.query().get('page'));return Number.isSafeInteger(value)&&value>0?value:1;});
}
