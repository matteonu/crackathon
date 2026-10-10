import { Component, ElementRef, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MaterialStore } from '../services/material-store';
import { MATERIAL_CATEGORIES, MATERIAL_MARKERS, MaterialCategory, MaterialMarker } from '../models/material';
import { MATERIAL_TOOLS } from '../services/study-demo.service';
import { MaterialToolComponent } from './material-tool.component';
import { IconComponent } from '../shared/icon.component';
import { PdfPreviewComponent } from './pdf-preview.component';

@Component({selector:'app-material-library',standalone:true,imports:[FormsModule,MaterialToolComponent,IconComponent,PdfPreviewComponent],template:`
  <section class="panel library-panel">
    <div class="panel-heading"><div><span class="eyebrow">YOUR LEARNING MATERIAL</span><h2>Materials library</h2><p>Keep your sources and next steps together.</p></div><span class="soft-badge">{{subjectFiles().length}} {{subjectFiles().length===1?'file':'files'}}</span></div>
    <div class="upload-zone" [class.dragging]="dragging()" (dragover)="$event.preventDefault();dragging.set(true)" (dragleave)="dragging.set(false)" (drop)="drop($event)">
      <app-icon name="upload" /><strong>Drop your PDFs here</strong><p>Slides, notes, transcripts, books, exams, and exercises.</p>
      <div class="upload-actions"><label class="sr-only" for="upload-category">Category for new files</label><select id="upload-category" [(ngModel)]="category">@for(c of categories;track c){<option>{{c}}</option>}</select>
      <label class="button primary import-button">{{materials.busy()?'Saving…':'Choose PDFs'}}<input aria-label="Upload PDFs" type="file" multiple accept=".pdf,application/pdf" [disabled]="materials.loading()||materials.busy()" (change)="upload($event)"></label></div>
      <small>Up to 50 MB per PDF · Stored in this browser</small>
    </div>
    <div class="library-filters"><input aria-label="Search materials" type="search" placeholder="Search materials…" [ngModel]="query()" (ngModelChange)="query.set($event)"><select aria-label="Filter by marker" [ngModel]="marker()" (ngModelChange)="marker.set($event)"><option value="">All markers</option>@for(m of markers;track m){<option>{{m}}</option>}</select></div>
    @if(materials.error()){<p class="form-error" role="alert">{{materials.error()}}</p>}
    @if(materials.loading()){<p class="empty-state">Loading your materials…</p>}
    @else{
      <div class="material-list">@for(file of filtered();track file.id){
        <article class="material-row"><button class="file-open" (click)="open(file.id)"><span class="pdf-icon">PDF</span><span><strong>{{file.name}}</strong><small>{{size(file.size)}} · {{file.category}}</small></span></button>
          <div class="material-row-controls"><select [attr.aria-label]="'Category for '+file.name" [ngModel]="file.category" (ngModelChange)="setCategory(file.id,$event)">@for(c of categories;track c){<option>{{c}}</option>}</select><select [attr.aria-label]="'Marker for '+file.name" [ngModel]="file.marker" (ngModelChange)="setMarker(file.id,$event)" [class.marker-done]="file.marker==='Done'">@for(m of markers;track m){<option>{{m}}</option>}</select></div>
        </article>
      }@empty{<div class="empty-state">{{subjectFiles().length?'No materials match your search.':'Add your first PDF to start building your study library.'}}</div>}</div>
    }
    <p class="field-hint library-note">PDFs stay on this device and are separate from the study-data JSON export.</p>
  </section>
  <dialog #preview class="edit-dialog material-dialog" aria-labelledby="material-title" (close)="selectedId.set(null)">
    @if(selected();as file){
      <div class="dialog-top"><span class="eyebrow">{{file.category}} · {{file.marker}}</span><button class="icon-button" aria-label="Close material" (click)="preview.close()"><app-icon name="close" /></button></div>
      <h2 id="material-title">{{file.name}}</h2>
      <div class="material-workspace"><div class="pdf-preview">
        <app-pdf-preview [blob]="file.blob" [name]="file.name" />
        <div class="preview-actions"><a class="button secondary" [href]="downloadUrl()" [download]="file.name">Download PDF</a><button class="text-button danger" (click)="remove(file.id)">Remove file</button></div>
      </div><div class="material-tools"><p class="demo-notice">Demo tools show example results. Your PDF is not analyzed or sent to a server.</p>
        @for(current of [file];track current.id){@for(tool of tools;track tool.id){<app-material-tool [file]="current" [tool]="tool.id" [title]="tool.title" [description]="tool.description" />}}
      </div></div>
    }
  </dialog>
`})
export class MaterialLibraryComponent {
  readonly subjectId=input.required<string>();readonly materials=inject(MaterialStore);
  readonly categories=MATERIAL_CATEGORIES;readonly markers=MATERIAL_MARKERS;readonly tools=MATERIAL_TOOLS;
  readonly preview=viewChild<ElementRef<HTMLDialogElement>>('preview');
  readonly query=signal('');readonly marker=signal('');readonly dragging=signal(false);readonly selectedId=signal<string|null>(null);
  readonly subjectFiles=computed(()=>this.materials.files().filter(f=>f.subjectId===this.subjectId()));
  readonly filtered=computed(()=>this.subjectFiles().filter(f=>f.name.toLowerCase().includes(this.query().toLowerCase())&&(!this.marker()||f.marker===this.marker())));
  readonly selected=computed(()=>this.subjectFiles().find(f=>f.id===this.selectedId()));
  private readonly selectedBlob=computed(()=>this.selected()?.blob);
  readonly downloadUrl=signal('');category:MaterialCategory='Slides';
  constructor(){effect(onCleanup=>{
    const blob=this.selectedBlob();if(!blob){this.downloadUrl.set('');return;}
    const url=URL.createObjectURL(blob);this.downloadUrl.set(url);
    onCleanup(()=>URL.revokeObjectURL(url));
  });}
  size(bytes:number):string{return bytes<1024*1024?`${Math.max(1,Math.round(bytes/1024))} KB`:`${(bytes/1024/1024).toFixed(1)} MB`;}
  open(id:string):void{this.selectedId.set(id);this.preview()?.nativeElement.showModal();}
  async upload(event:Event):Promise<void>{const input=event.target as HTMLInputElement;await this.materials.add(this.subjectId(),Array.from(input.files??[]),this.category);input.value='';}
  async drop(event:DragEvent):Promise<void>{event.preventDefault();this.dragging.set(false);await this.materials.add(this.subjectId(),Array.from(event.dataTransfer?.files??[]),this.category);}
  setMarker(id:string,marker:MaterialMarker):void{void this.materials.update(id,{marker});}
  setCategory(id:string,category:MaterialCategory):void{void this.materials.update(id,{category});}
  async remove(id:string):Promise<void>{await this.materials.remove(id);if(!this.materials.files().some(f=>f.id===id))this.preview()?.nativeElement.close();}
}
