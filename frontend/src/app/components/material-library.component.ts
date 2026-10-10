import { Component, ElementRef, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MaterialStore } from '../services/material-store';
import { MATERIAL_MARKERS, MaterialKind, MaterialMarker, materialKind, folderCards, treeRows } from '../models/material';
import { IconComponent } from '../shared/icon.component';
import { FileViewerComponent } from './file-viewer.component';
import { FolderFlashcardsComponent } from './folder-flashcards.component';
import { FlashcardExportService } from '../services/flashcard-export.service';

@Component({selector:'app-material-library',standalone:true,imports:[FormsModule,IconComponent,FileViewerComponent,FolderFlashcardsComponent],templateUrl:'./material-library.component.html'})
export class MaterialLibraryComponent {
  readonly subjectId=input.required<string>();readonly materials=inject(MaterialStore);private readonly exporter=inject(FlashcardExportService);
  readonly preview=viewChild<ElementRef<HTMLDialogElement>>('preview');readonly createDialog=viewChild<ElementRef<HTMLDialogElement>>('createDialog');readonly collectionDialog=viewChild<ElementRef<HTMLDialogElement>>('collectionDialog');
  readonly practice=viewChild(FolderFlashcardsComponent);
  readonly markers=MATERIAL_MARKERS;readonly kind=materialKind;
  readonly query=signal('');readonly marker=signal('');readonly dragging=signal(false);readonly selectedId=signal<string|null>(null);readonly activeFolder=signal<string|null>(null);readonly expanded=signal(new Set<string>());
  readonly subjectFiles=computed(()=>this.materials.files().filter(f=>f.subjectId===this.subjectId()));
  readonly selected=computed(()=>this.subjectFiles().find(f=>f.id===this.selectedId()));
  readonly rows=computed(()=>treeRows(this.subjectFiles(),this.expanded(),this.query(),this.marker()));
  readonly fileCount=computed(()=>this.subjectFiles().filter(f=>materialKind(f)!=='folder').length);
  readonly folderName=computed(()=>this.subjectFiles().find(f=>f.id===this.activeFolder())?.name??'Materials');
  readonly breadcrumbs=computed(()=>{const parts:{id:string|null;name:string}[]=[];let id=this.activeFolder();const seen=new Set<string>();while(id&&!seen.has(id)){seen.add(id);const f=this.subjectFiles().find(f=>f.id===id);if(!f)break;parts.unshift({id:f.id,name:f.name});id=f.parentId??null;}return [{id:null,name:'Materials'},...parts];});
  readonly collectionFolder=signal<string|null>(null);readonly collectionOpen=signal(false);readonly collectionCards=computed(()=>folderCards(this.subjectFiles(),this.collectionFolder()));readonly collectionName=computed(()=>this.subjectFiles().find(f=>f.id===this.collectionFolder())?.name??'Materials');
  readonly exporting=signal(false);readonly localError=signal('');readonly status=signal('');readonly creating=signal(false);readonly creationError=signal('');
  createType:Exclude<MaterialKind,'pdf'>='folder';newName='';private createParent:string|null=null;
  constructor(){effect(()=>{this.subjectId();this.activeFolder.set(null);this.selectedId.set(null);this.expanded.set(new Set());this.query.set('');this.marker.set('');});}
  count(folderId:string|null):number{return folderCards(this.subjectFiles(),folderId).length;}
  chooseFolder(id:string|null):void{this.activeFolder.set(id);if(id)this.expanded.update(s=>new Set([...s,id]));}
  toggle(id:string):void{this.expanded.update(s=>{const next=new Set(s);next.has(id)?next.delete(id):next.add(id);return next;});}
  open(id:string):void{this.selectedId.set(id);this.preview()?.nativeElement.showModal();}
  newItem(kind:Exclude<MaterialKind,'pdf'>):void{this.createType=kind;this.newName='';this.createParent=this.activeFolder();this.creationError.set('');this.createDialog()?.nativeElement.showModal();}
  selectType(event:Event):void{const input=event.target as HTMLSelectElement;if(input.value)this.newItem(input.value as Exclude<MaterialKind,'pdf'>);input.value='';}
  async create():Promise<void>{this.creating.set(true);try{const file=await this.materials.create(this.subjectId(),this.createParent,this.createType,this.newName);if(this.createParent)this.expanded.update(s=>new Set([...s,this.createParent!]));this.createDialog()?.nativeElement.close();if(file.kind==='folder')this.chooseFolder(file.id);else this.open(file.id);this.status.set(`${file.name} created.`);}catch(e){this.creationError.set(e instanceof Error?e.message:'Could not create item.');}finally{this.creating.set(false);}}
  async upload(event:Event):Promise<void>{const input=event.target as HTMLInputElement;await this.materials.add(this.subjectId(),Array.from(input.files??[]),'Slides',this.activeFolder());input.value='';}
  async drop(event:DragEvent):Promise<void>{event.preventDefault();this.dragging.set(false);await this.materials.add(this.subjectId(),Array.from(event.dataTransfer?.files??[]),'Slides',this.activeFolder());}
  setMarker(id:string,value:MaterialMarker):void{void this.materials.update(id,{marker:value});}
  showCards(id:string|null,learn=false):void{this.collectionFolder.set(id);this.collectionOpen.set(true);this.collectionDialog()?.nativeElement.showModal();if(learn)requestAnimationFrame(()=>this.practice()?.start());}
  openSource(id:string):void{this.collectionDialog()?.nativeElement.close();this.open(id);}
  async exportFolder(id:string|null):Promise<void>{if(this.exporting())return;const name=this.subjectFiles().find(f=>f.id===id)?.name??'Materials';const cards=folderCards(this.subjectFiles(),id);this.exporting.set(true);this.localError.set('');try{await this.exporter.export(cards,name,`${this.subjectId()}:${id??'root'}`);this.status.set(`${cards.length} flashcards exported as ${name}.apkg.`);}catch(e){this.localError.set(e instanceof Error?e.message:'Export failed. Please retry.');}finally{this.exporting.set(false);}}
}
