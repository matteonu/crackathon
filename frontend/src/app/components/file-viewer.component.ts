import { Component, ElementRef, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MaterialStore } from '../services/material-store';
import { LearningMode, canGenerateFlashcards, canChatWithDocument, materialFileUrl, materialKind } from '../models/material';
import { DocumentChatComponent } from './document-chat.component';
import { PdfPreviewComponent } from './pdf-preview.component';
import { IconComponent } from '../shared/icon.component';
import { LoadingDotsComponent } from '../shared/loading-dots.component';
import { LearningModeComponent } from '../shared/learning-mode.component';

@Component({selector:'app-file-viewer',standalone:true,imports:[FormsModule,ReactiveFormsModule,PdfPreviewComponent,IconComponent,LoadingDotsComponent,LearningModeComponent,DocumentChatComponent],templateUrl:'./file-viewer.component.html'})
export class FileViewerComponent {
  readonly fileId=input.required<string>();readonly materials=inject(MaterialStore);
  readonly selectedMode=signal<LearningMode>('shallow');
  readonly requestedCount=signal<number|null>(60);
  readonly validCount=computed(()=>Number.isInteger(this.requestedCount())&&this.requestedCount()!>=5&&this.requestedCount()!<=300);
  readonly allowsCards=computed(()=>!!this.file()&&(this.kind()!=='pdf'||canGenerateFlashcards(this.file()!)));
  readonly allowsChat=computed(()=>!!this.file()&&canChatWithDocument(this.file()!));
  readonly pageContext=signal({page:0,total:0});
  readonly panelChoice=signal<'flashcards'|'chat'|null>(null);
  readonly panel=computed(()=>!this.allowsChat()?'flashcards':!this.allowsCards()?'chat':this.panelChoice()??(this.cards().length?'flashcards':'chat'));
  readonly summaryRunning=computed(()=>this.generating()&&this.file()?.processing?.task==='summary');
  readonly cardsReady=computed(()=>this.file()?.processing?.task!=='summary'&&this.file()?.processing?.status==='complete'&&this.selectedMode()===(this.file()?.processing?.mode??'shallow')&&this.requestedCount()===(this.file()?.processing?.requestedQuestions??60));
  readonly stage=viewChild<ElementRef<HTMLElement>>('stage');
  readonly file=computed(()=>this.materials.files().find(f=>f.id===this.fileId()));readonly kind=computed(()=>this.file()?materialKind(this.file()!):'pdf');
  readonly cards=computed(()=>this.file()?.outputs?.flashcards?.cards??[]);readonly selectedCard=signal<string|null>(null);readonly card=computed(()=>this.cards().find(c=>c.id===this.selectedCard()));
  readonly revealed=signal(false);readonly generating=computed(()=>['queued','running'].includes(this.file()?.processing?.status??''));readonly saving=signal(false);readonly editing=signal(false);readonly addingCard=signal(false);
  readonly error=signal('');readonly notice=signal('');readonly fileUrl=computed(()=>materialFileUrl(this.fileId()));
  readonly details=new FormGroup({name:new FormControl('',{nonNullable:true}),description:new FormControl('',{nonNullable:true})});
  readonly content=new FormControl('',{nonNullable:true});readonly cardForm=new FormGroup({question:new FormControl('',{nonNullable:true}),answer:new FormControl('',{nonNullable:true})});
  readonly lines=computed(()=>(this.file()?.content??'').split('\n'));
  constructor(){
    effect(()=>{this.fileId();this.panelChoice.set(null);this.pageContext.set({page:0,total:0});this.returnToFile();});
    effect(()=>{const id=this.fileId();const f=this.materials.files().find(f=>f.id===id);if(f&&!this.loaded.has(id)){this.loaded.add(id);this.selectedMode.set(f.processing?.task==='summary'?'shallow':f.processing?.mode??'shallow');this.requestedCount.set(f.processing?.requestedQuestions||60);this.details.reset({name:f.name,description:f.description??''});this.content.setValue(f.content??'');}});
  }
  private readonly loaded=new Set<string>();
  choosePanel(panel:'flashcards'|'chat'):void{this.panelChoice.set(panel);this.returnToFile();}
  selectCard(id:string):void{this.selectedCard.set(id);this.revealed.set(false);requestAnimationFrame(()=>this.stage()?.nativeElement.scrollIntoView({block:'nearest'}));}
  returnToFile():void{this.selectedCard.set(null);this.revealed.set(false);}
  surfaceClick(event:MouseEvent):void{const target=event.target;if(target instanceof Element&&!target.closest('.flashcard-stage, .flashcard-choice'))this.returnToFile();}
  escape(event:Event):void{if(this.selectedCard()){event.preventDefault();event.stopPropagation();this.returnToFile();}}
  async saveDetails():Promise<void>{const value=this.details.getRawValue();if(this.kind()==='pdf'&&value.name===this.file()?.name)return;this.saving.set(true);this.error.set('');const ok=await this.materials.update(this.fileId(),this.kind()==='pdf'?{name:value.name}:value);this.saving.set(false);if(ok){this.details.controls.name.setValue(this.file()!.name);this.notice.set('File details saved.');}else this.error.set(this.materials.error());}
  async generate():Promise<void>{if(!this.validCount()||!this.allowsCards()||this.generating())return;this.error.set('');this.returnToFile();await this.materials.process(this.fileId(),false,this.selectedMode(),this.requestedCount()!,'flashcards');}
  async summarize():Promise<void>{this.error.set('');await this.materials.process(this.fileId(),false,'deep',undefined,'summary');}
  async addCard():Promise<void>{const value=this.cardForm.getRawValue();if(!value.question.trim()||!value.answer.trim()){this.error.set('Enter a question and an answer.');return;}if(await this.materials.appendCards(this.fileId(),[{question:value.question.trim(),answer:value.answer.trim(),demo:false}])){this.cardForm.reset();this.addingCard.set(false);this.error.set('');}else this.error.set(this.materials.error());}
  async saveContent():Promise<void>{if(await this.materials.update(this.fileId(),{content:this.content.value})){this.editing.set(false);this.notice.set('File content saved.');}else this.error.set(this.materials.error());}
  cancelContent():void{this.content.setValue(this.file()?.content??'');this.editing.set(false);}
  heading(line:string):number{return /^(#{1,3}) /.exec(line)?.[1].length??0;}
  text(line:string):string{return line.replace(/^#{1,3} /,'').replace(/^- /,'• ');}
}
