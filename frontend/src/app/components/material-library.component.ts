import { Component, DestroyRef, ElementRef, Injector, afterNextRender, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MaterialStore } from '../services/material-store';
import { MATERIAL_MARKERS, Material, MaterialKind, MaterialMarker, MaterialCategory, UPLOAD_CATEGORIES, materialKind, materialListType, materialListTypeLabel, materialCards, materialPath, folderCards, treeRows, validParent } from '../models/material';
import { IconComponent } from '../shared/icon.component';
import { FileViewerComponent } from './file-viewer.component';
import { FolderFlashcardsComponent } from './folder-flashcards.component';
import { FlashcardExportService } from '../services/flashcard-export.service';
import { LoadingDotsComponent } from '../shared/loading-dots.component';
import { GenerationLoaderComponent } from '../shared/generation-loader.component';

@Component({selector:'app-material-library',standalone:true,imports:[FormsModule,IconComponent,FileViewerComponent,FolderFlashcardsComponent,LoadingDotsComponent,GenerationLoaderComponent],templateUrl:'./material-library.component.html'})
export class MaterialLibraryComponent {
  readonly subjectId=input.required<string>();readonly materials=inject(MaterialStore);private readonly exporter=inject(FlashcardExportService);
  readonly preview=viewChild<ElementRef<HTMLDialogElement>>('preview');readonly createDialog=viewChild<ElementRef<HTMLDialogElement>>('createDialog');readonly collectionDialog=viewChild<ElementRef<HTMLDialogElement>>('collectionDialog');readonly learningDialog=viewChild<ElementRef<HTMLDialogElement>>('learningDialog');
  readonly markers=MATERIAL_MARKERS;readonly kind=materialKind;readonly typeLabel=materialListTypeLabel;readonly documentType=materialListType;
  readonly uploadCategories=UPLOAD_CATEGORIES;readonly uploadCategory=signal<MaterialCategory>('Slides');
  private uploadParent:string|null=null;
  private openRequest=0;
  private readonly injector=inject(Injector);
  private openTimer:ReturnType<typeof setTimeout>|undefined;
  readonly renameDialog=viewChild<ElementRef<HTMLDialogElement>>('renameDialog');
  readonly renameInput=viewChild<ElementRef<HTMLInputElement>>('renameInput');
  readonly renameId=signal<string|null>(null);readonly savingRename=signal(false);readonly renameError=signal('');
  readonly renameTarget=computed(()=>this.subjectFiles().find(file=>file.id===this.renameId()));
  renameDraft='';
  prepareUpload(category:MaterialCategory):void{this.uploadCategory.set(category);this.uploadParent=this.activeFolder();}
  readonly deleting=signal(new Set<string>());
  readonly deleteDialog=viewChild<ElementRef<HTMLDialogElement>>('deleteDialog');readonly pendingDelete=signal<Material|null>(null);
  readonly query=signal('');readonly marker=signal('');readonly dragging=signal(false);readonly selectedId=signal<string|null>(null);readonly activeFolder=signal<string|null>(null);readonly expanded=signal(new Set<string>());
  readonly subjectFiles=computed(()=>this.materials.files().filter(f=>f.subjectId===this.subjectId()));
  readonly selected=computed(()=>this.subjectFiles().find(f=>f.id===this.selectedId()));
  readonly selectedPath=computed(()=>this.selected()?materialPath(this.subjectFiles(),this.selected()!):'Materials');
  readonly draggedFile=signal<string|null>(null);readonly dropFolder=signal<string|null|undefined>(undefined);readonly movingFile=signal<string|null>(null);
  readonly rows=computed(()=>treeRows(this.subjectFiles(),this.expanded(),this.query(),this.marker()));
  readonly folderName=computed(()=>this.subjectFiles().find(f=>f.id===this.activeFolder())?.name??'Materials');
  readonly collectionFolder=signal<string|null>(null);readonly collectionOpen=signal(false);readonly collectionCards=computed(()=>folderCards(this.subjectFiles(),this.collectionFolder()));readonly collectionName=computed(()=>this.subjectFiles().find(f=>f.id===this.collectionFolder())?.name??'Materials');
  readonly learningFolder=signal<string|null>(null);readonly learningDeck=signal<string|null>(null);readonly learningOpen=signal(false);
  readonly learningName=computed(()=>this.subjectFiles().find(f=>f.id===(this.learningDeck()??this.learningFolder()))?.name??'Materials');
  readonly learningCards=computed(()=>this.learningDeck()?folderCards(this.subjectFiles(),null).filter(c=>c.deckId===this.learningDeck()):folderCards(this.subjectFiles(),this.learningFolder()));
  readonly exporting=signal(false);readonly localError=signal('');readonly status=signal('');readonly creating=signal(false);readonly creationError=signal('');
  createType:Exclude<MaterialKind,'pdf'|'deck'>='folder';newName='';private createParent:string|null=null;
  constructor(){
    inject(DestroyRef).onDestroy(()=>this.cancelPendingOpen());
    effect(()=>{this.subjectId();this.cancelPendingOpen();this.renameDialog()?.nativeElement.close();this.renameId.set(null);this.endFileDrag();this.activeFolder.set(null);this.selectedId.set(null);this.expanded.set(new Set());this.query.set('');this.marker.set('');});
    effect(()=>{
      const ids=new Set(this.subjectFiles().map(file=>file.id));
      if(this.selectedId()&&!ids.has(this.selectedId()!)){this.preview()?.nativeElement.close();this.selectedId.set(null);}
      if(this.activeFolder()&&!ids.has(this.activeFolder()!))this.activeFolder.set(null);
      if(this.collectionFolder()&&!ids.has(this.collectionFolder()!)){this.collectionDialog()?.nativeElement.close();this.collectionFolder.set(null);this.collectionOpen.set(false);}
      const learningId=this.learningDeck()??this.learningFolder();
      if(learningId&&!ids.has(learningId)){this.learningDialog()?.nativeElement.close();this.learningOpen.set(false);}
      if(this.pendingDelete()&&!ids.has(this.pendingDelete()!.id)){this.deleteDialog()?.nativeElement.close();this.pendingDelete.set(null);}
      if(this.renameId()&&!ids.has(this.renameId()!)){this.renameDialog()?.nativeElement.close();this.renameId.set(null);}
    });
  }
  count(folderId:string|null):number{return folderCards(this.subjectFiles(),folderId).length;}
  private cancelPendingOpen():void{clearTimeout(this.openTimer);this.openTimer=undefined;}
  clickMaterial(event:MouseEvent,file:Material):void{
    this.cancelPendingOpen();
    if(this.draggedFile()||this.deleting().has(file.id)||event.detail>1)return;
    if(materialKind(file)==='folder'){this.chooseFolder(file.id);return;}
    // Mouse clicks wait for the double-click gesture; keyboard activation stays immediate.
    if(!['pdf','deck'].includes(materialKind(file))||event.detail===0){void this.open(file.id);return;}
    this.openTimer=setTimeout(()=>void this.open(file.id),500);
  }
  beginRename(event:Event,file:Material):void{
    if(!['folder','pdf','deck'].includes(materialKind(file)))return;
    event.preventDefault();event.stopPropagation();this.cancelPendingOpen();
    if(this.savingRename()||this.draggedFile()||this.movingFile()||this.deleting().has(file.id))return;
    this.renameDraft=file.name;this.renameError.set('');this.renameId.set(file.id);
    this.renameDialog()?.nativeElement.showModal();
    afterNextRender(()=>{
      if(this.renameId()!==file.id)return;
      const field=this.renameInput()?.nativeElement;if(!field)return;
      field.focus();field.setSelectionRange(0,materialKind(file)==='pdf'?file.name.length-4:file.name.length);
    },{injector:this.injector});
  }
  async saveRename():Promise<void>{
    const file=this.renameTarget();if(!file||this.savingRename())return;
    this.savingRename.set(true);this.renameError.set('');
    try{
      if(await this.materials.update(file.id,{name:this.renameDraft})){
        this.renameDialog()?.nativeElement.close();
        this.renameId.set(null);
        this.status.set(`Renamed to ${this.subjectFiles().find(item=>item.id===file.id)?.name??this.renameDraft}.`);
      }else this.renameError.set(this.materials.error()||'Could not rename this item. Please retry.');
    }finally{this.savingRename.set(false);}
  }
  chooseFolder(id:string|null):void{this.cancelPendingOpen();this.activeFolder.set(id);if(id)this.expanded.update(s=>new Set([...s,id]));}
  toggle(id:string):void{this.expanded.update(s=>{const next=new Set(s);next.has(id)?next.delete(id):next.add(id);return next;});}
  async open(id:string):Promise<void>{
    this.cancelPendingOpen();
    const request=++this.openRequest,subject=this.subjectId();
    const cached=this.subjectFiles().some(file=>file.id===id);
    if(cached){
      this.selectedId.set(id);this.preview()?.nativeElement.showModal();
    }
    // Refresh after opening; a confirmed deletion removes the file and the
    // existing selection effect closes its viewer. Transient failures keep it open.
    const available=await this.materials.ensureAvailable(id);
    // References missing from the local list still need their details first.
    // A late response must not replace a more recently opened file.
    if(!cached&&available&&request===this.openRequest&&subject===this.subjectId()
      &&this.subjectFiles().some(file=>file.id===id)){
      this.selectedId.set(id);this.preview()?.nativeElement.showModal();
    }
  }
  newItem(kind:Exclude<MaterialKind,'pdf'|'deck'>,parentId:string|null):void{this.chooseFolder(parentId);this.createType=kind;this.newName='';this.createParent=parentId;this.creationError.set('');this.createDialog()?.nativeElement.showModal();}
  async create():Promise<void>{this.creating.set(true);try{const file=await this.materials.create(this.subjectId(),this.createParent,this.createType,this.newName);if(this.createParent)this.expanded.update(s=>new Set([...s,this.createParent!]));this.createDialog()?.nativeElement.close();if(file.kind==='folder')this.chooseFolder(file.id);else this.open(file.id);this.status.set(`${file.name} created.`);}catch(e){this.creationError.set(e instanceof Error?e.message:'Could not create item.');}finally{this.creating.set(false);}}
  async upload(event:Event):Promise<void>{const input=event.target as HTMLInputElement;await this.materials.add(this.subjectId(),Array.from(input.files??[]),this.uploadCategory(),this.uploadParent);input.value='';}
  startFileDrag(event:DragEvent,id:string):void{
    this.cancelPendingOpen();
    if(this.movingFile()||this.deleting().has(id)||!event.dataTransfer){event.preventDefault();return;}
    this.draggedFile.set(id);event.dataTransfer.effectAllowed='move';
    event.dataTransfer.setData('application/x-studyhub-material',id);
  }
  endFileDrag():void{this.draggedFile.set(null);this.dropFolder.set(undefined);this.dragging.set(false);}
  dragOver(event:DragEvent):void{
    event.preventDefault();if(event.dataTransfer)event.dataTransfer.dropEffect=this.draggedFile()?'move':'copy';
    this.dropFolder.set(undefined);this.dragging.set(!this.draggedFile());
  }
  dragOverFolder(event:DragEvent,id:string|null):void{
    if(!this.draggedFile()&&!event.dataTransfer?.types.includes('Files'))return;
    event.preventDefault();event.stopPropagation();this.dropFolder.set(id);
    if(event.dataTransfer)event.dataTransfer.dropEffect=this.draggedFile()?'move':'copy';
  }
  leaveFolder(event:DragEvent):void{
    if(event.currentTarget instanceof Element&&event.relatedTarget instanceof Node&&event.currentTarget.contains(event.relatedTarget))return;
    this.dropFolder.set(undefined);
  }
  async drop(event:DragEvent,parentId:string|null=this.activeFolder()):Promise<void>{
    event.preventDefault();event.stopPropagation();const id=this.draggedFile();this.endFileDrag();
    if(id){
      const file=this.subjectFiles().find(f=>f.id===id);
      if(!file||materialKind(file)==='folder'||this.movingFile()||(file.parentId??null)===parentId)return;
      if(!validParent(this.subjectFiles(),this.subjectId(),parentId,id))return;
      this.movingFile.set(id);this.localError.set('');
      try{
        if(await this.materials.update(id,{parentId})){
          if(parentId)this.expanded.update(s=>new Set([...s,parentId]));
          this.status.set(`${file.name} moved to ${this.subjectFiles().find(f=>f.id===parentId)?.name??'Materials'}.`);
        }else this.localError.set(this.materials.error());
      }finally{this.movingFile.set(null);}
    }else await this.materials.add(this.subjectId(),Array.from(event.dataTransfer?.files??[]),this.uploadCategory(),parentId);
  }
  requestFolderDelete(id:string):void{this.cancelPendingOpen();const file=this.subjectFiles().find(file=>file.id===id);if(!file||materialKind(file)!=='folder')return;this.pendingDelete.set(file);this.deleteDialog()?.nativeElement.showModal();}
  async confirmFolderDelete():Promise<void>{const file=this.pendingDelete();if(file&&await this.remove(file.id)){this.deleteDialog()?.nativeElement.close();this.pendingDelete.set(null);}}
  async remove(id:string):Promise<boolean>{
    this.cancelPendingOpen();
    if(this.deleting().has(id))return false;const file=this.subjectFiles().find(f=>f.id===id);if(!file)return true;
    this.deleting.update(ids=>new Set([...ids,id]));
    try{if(await this.materials.remove(id)){if(this.selectedId()===id)this.preview()?.nativeElement.close();this.status.set(`${file.name} deleted.`);return true;}return false;}
    finally{this.deleting.update(ids=>{const next=new Set(ids);next.delete(id);return next;});}
  }
  setMarker(id:string,value:MaterialMarker):void{void this.materials.update(id,{marker:value});}
  showCards(id:string|null,learn=false):void{this.cancelPendingOpen();if(learn){this.startLearning(id);return;}this.collectionFolder.set(id);this.collectionOpen.set(true);this.collectionDialog()?.nativeElement.showModal();}
  startLearning(folderId:string|null,deckId:string|null=null):void{
    this.cancelPendingOpen();
    this.collectionDialog()?.nativeElement.close();this.preview()?.nativeElement.close();
    this.learningFolder.set(folderId);this.learningDeck.set(deckId);this.learningOpen.set(true);this.learningDialog()?.nativeElement.showModal();
  }
  openSource(id:string):void{this.collectionDialog()?.nativeElement.close();this.open(id);}
  async exportCards(id:string|null):Promise<void>{
    if(this.exporting())return;
    const files=this.subjectFiles(),item=files.find(f=>f.id===id),name=item?.name??'Materials';
    // Export the whole collection, regardless of visible rows, markers, or session limits.
    const cards=item&&materialKind(item)==='deck'?materialCards(item):folderCards(files,id);
    this.exporting.set(true);this.localError.set('');
    try{await this.exporter.export(cards,name,`${this.subjectId()}:${id??'root'}`);this.status.set(`${cards.length} flashcards exported as ${name}.apkg.`);}
    catch(e){this.localError.set(e instanceof Error?e.message:'Export failed. Please retry.');}
    finally{this.exporting.set(false);}
  }
}
