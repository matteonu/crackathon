import { Component, ElementRef, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MaterialStore } from '../services/material-store';
import { StudyDemoService } from '../services/study-demo.service';
import { MATERIAL_MARKERS, MaterialMarker, materialKind } from '../models/material';
import { PdfPreviewComponent } from './pdf-preview.component';
import { IconComponent } from '../shared/icon.component';

@Component({selector:'app-file-viewer',standalone:true,imports:[FormsModule,ReactiveFormsModule,PdfPreviewComponent,IconComponent],templateUrl:'./file-viewer.component.html'})
export class FileViewerComponent {
  readonly fileId=input.required<string>();readonly materials=inject(MaterialStore);private readonly demo=inject(StudyDemoService);
  readonly stage=viewChild<ElementRef<HTMLElement>>('stage');
  readonly file=computed(()=>this.materials.files().find(f=>f.id===this.fileId()));readonly kind=computed(()=>this.file()?materialKind(this.file()!):'pdf');
  readonly cards=computed(()=>this.file()?.outputs?.flashcards?.cards??[]);readonly selectedCard=signal<string|null>(null);readonly card=computed(()=>this.cards().find(c=>c.id===this.selectedCard()));
  readonly revealed=signal(false);readonly generating=signal(false);readonly describing=signal(false);readonly saving=signal(false);readonly editing=signal(false);readonly addingCard=signal(false);
  readonly error=signal('');readonly notice=signal('');readonly downloadUrl=signal('');readonly markers=MATERIAL_MARKERS;
  readonly details=new FormGroup({name:new FormControl('',{nonNullable:true}),description:new FormControl('',{nonNullable:true})});
  readonly content=new FormControl('',{nonNullable:true});readonly cardForm=new FormGroup({question:new FormControl('',{nonNullable:true}),answer:new FormControl('',{nonNullable:true})});
  readonly folders=computed(()=>this.materials.files().filter(f=>f.subjectId===this.file()?.subjectId&&materialKind(f)==='folder'));
  private readonly blob=computed(()=>this.file()?.blob);
  readonly lines=computed(()=>(this.file()?.content??'').split('\n'));
  constructor(){
    effect(()=>{const id=this.fileId();const f=this.materials.files().find(f=>f.id===id);if(f&&!this.loaded.has(id)){this.loaded.add(id);this.details.reset({name:f.name,description:f.description??''});this.content.setValue(f.content??'');}});
    effect(onCleanup=>{const blob=this.blob();if(!blob)return;const url=URL.createObjectURL(blob);this.downloadUrl.set(url);onCleanup(()=>URL.revokeObjectURL(url));});
  }
  private readonly loaded=new Set<string>();
  selectCard(id:string):void{this.selectedCard.set(id);this.revealed.set(false);requestAnimationFrame(()=>this.stage()?.nativeElement.scrollIntoView({block:'nearest'}));}
  returnToFile():void{this.selectedCard.set(null);this.revealed.set(false);}
  surfaceClick(event:MouseEvent):void{const target=event.target;if(target instanceof Element&&!target.closest('.flashcard-stage, .flashcard-choice'))this.returnToFile();}
  escape(event:Event):void{if(this.selectedCard()){event.preventDefault();event.stopPropagation();this.returnToFile();}}
  async saveDetails():Promise<void>{this.saving.set(true);this.error.set('');const ok=await this.materials.update(this.fileId(),this.details.getRawValue());this.saving.set(false);if(ok){this.details.controls.name.setValue(this.file()!.name);this.notice.set('File details saved.');}else this.error.set(this.materials.error());}
  async autoDescribe():Promise<void>{const file=this.file();if(!file)return;this.describing.set(true);this.error.set('');try{await this.demo.generate('summary',file);this.details.controls.description.setValue(`Demo description: Key concepts, examples, and review prompts for ${file.name}.`);this.notice.set('Demo description filled in. Edit it and save when ready.');}catch{this.error.set('Could not fill the description. Try again.');}finally{this.describing.set(false);}}
  async generate():Promise<void>{const file=this.file();if(!file)return;this.generating.set(true);this.error.set('');try{const result=await this.demo.generate('flashcards',file);if(!await this.materials.appendCards(file.id,(result.cards??[]).map(c=>({...c,demo:true}))))throw new Error();this.notice.set('Demo flashcards added.');}catch{this.error.set('Could not generate or save cards. Try again.');}finally{this.generating.set(false);}}
  async addCard():Promise<void>{const value=this.cardForm.getRawValue();if(!value.question.trim()||!value.answer.trim()){this.error.set('Enter a question and an answer.');return;}if(await this.materials.appendCards(this.fileId(),[{question:value.question.trim(),answer:value.answer.trim(),demo:false}])){this.cardForm.reset();this.addingCard.set(false);this.error.set('');}else this.error.set(this.materials.error());}
  async saveContent():Promise<void>{if(await this.materials.update(this.fileId(),{content:this.content.value})){this.editing.set(false);this.notice.set('File content saved.');}else this.error.set(this.materials.error());}
  cancelContent():void{this.content.setValue(this.file()?.content??'');this.editing.set(false);}
  move(parentId:string):void{void this.materials.update(this.fileId(),{parentId:parentId||null});}
  marker(marker:MaterialMarker):void{void this.materials.update(this.fileId(),{marker});}
  heading(line:string):number{return /^(#{1,3}) /.exec(line)?.[1].length??0;}
  text(line:string):string{return line.replace(/^#{1,3} /,'').replace(/^- /,'• ');}
}
