import { Component, ElementRef, computed, effect, inject, input, output, signal, viewChild } from '@angular/core';
import { FormControl, FormGroup, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MaterialStore } from '../services/material-store';
import { LearningMode, canGenerateFlashcards, canChatWithDocument, materialFileUrl, materialKind } from '../models/material';
import { DocumentChatComponent } from './document-chat.component';
import { PdfPreviewComponent } from './pdf-preview.component';
import { IconComponent } from '../shared/icon.component';
import { LoadingDotsComponent } from '../shared/loading-dots.component';
import { LearningModeComponent } from '../shared/learning-mode.component';
import { FolderFlashcardsComponent } from './folder-flashcards.component';
import { McqService } from '../services/mcq.service';
import { McqAnswerResult, McqSession, McqSet } from '../models/mcq';

@Component({selector:'app-file-viewer',standalone:true,imports:[FormsModule,ReactiveFormsModule,PdfPreviewComponent,IconComponent,LoadingDotsComponent,LearningModeComponent,FolderFlashcardsComponent,DocumentChatComponent],templateUrl:'./file-viewer.component.html'})
export class FileViewerComponent {
  readonly fileId=input.required<string>();readonly materials=inject(MaterialStore);
  readonly openFile=output<string>();
  readonly startLearning=output<string>();
  readonly mcq=inject(McqService);readonly tool=signal<'flashcards'|'mcq'|'chat'>('flashcards');
  readonly mcqSets=signal<McqSet[]>([]);readonly mcqLoading=signal(false);readonly mcqBusy=signal(false);
  readonly requestedMcqCount=signal<number|null>(null);
  readonly validMcqCount=computed(()=>this.requestedMcqCount()===null||(Number.isInteger(this.requestedMcqCount())&&this.requestedMcqCount()!>=1&&this.requestedMcqCount()!<=60));
  readonly mcqGenerating=computed(()=>this.mcqSets().some(s=>s.status==='queued'||s.status==='running'));
  readonly mcqSession=signal<McqSession|null>(null);readonly mcqFeedback=signal<McqAnswerResult|null>(null);
  readonly selectedOptions=signal<Set<string>>(new Set());
  readonly selectedMode=signal<LearningMode>('shallow');
  readonly requestedCount=signal<number|null>(60);
  readonly validCount=computed(()=>Number.isInteger(this.requestedCount())&&this.requestedCount()!>=5&&this.requestedCount()!<=300);
  readonly allowsCards=computed(()=>!!this.file()&&(this.kind()!=='pdf'||canGenerateFlashcards(this.file()!)));
  readonly allowsChat=computed(()=>!!this.file()&&canChatWithDocument(this.file()!));
  readonly pageContext=signal({page:0,total:0});
  readonly allowsMcq=computed(()=>this.kind()==='pdf'&&['Slides','Scripts'].includes(this.file()?.category??''));
  readonly currentMcq=computed(()=>{const s=this.mcqSession();return s?.questions[s.position]??null;});
  readonly displayedMcq=computed(()=>{const s=this.mcqSession();if(!s)return null;return s.questions[this.mcqFeedback()?Math.max(0,s.position-1):s.position]??null;});
  readonly summaryRunning=computed(()=>this.generating()&&this.file()?.processing?.task==='summary');
  readonly cardsReady=computed(()=>this.file()?.processing?.task!=='summary'&&this.file()?.processing?.status==='complete'&&this.selectedMode()===(this.file()?.processing?.mode??'shallow')&&this.requestedCount()===(this.file()?.processing?.requestedQuestions??60));
  readonly stage=viewChild<ElementRef<HTMLElement>>('stage');
  readonly file=computed(()=>this.materials.files().find(f=>f.id===this.fileId()));readonly kind=computed(()=>this.file()?materialKind(this.file()!):'pdf');
  readonly linkedDeck=computed(()=>this.materials.files().find(f=>f.kind==='deck'&&f.sourcePdfId===this.fileId()));
  readonly cards=computed(()=>(this.kind()==='pdf'?this.linkedDeck():this.file())?.outputs?.flashcards?.cards??[]);readonly selectedCard=signal<string|null>(null);readonly card=computed(()=>this.cards().find(c=>c.id===this.selectedCard()));
  readonly folders=computed(()=>this.materials.files().filter(f=>f.kind==='folder'&&f.subjectId===this.file()?.subjectId));
  readonly deckCards=computed(()=>this.cards().map(c=>({...c,key:c.id!,fileId:this.file()?.sourcePdfId??this.fileId(),fileName:this.file()?.name??'',deckId:this.fileId()})));
  readonly revealed=signal(false);readonly generating=computed(()=>['queued','running'].includes(this.file()?.processing?.status??''));readonly saving=signal(false);readonly editing=signal(false);readonly addingCard=signal(false);
  readonly error=signal('');readonly notice=signal('');readonly fileUrl=computed(()=>materialFileUrl(this.fileId()));
  readonly details=new FormGroup({name:new FormControl('',{nonNullable:true}),description:new FormControl('',{nonNullable:true})});
  readonly content=new FormControl('',{nonNullable:true});readonly cardForm=new FormGroup({question:new FormControl('',{nonNullable:true}),answer:new FormControl('',{nonNullable:true})});
  readonly lines=computed(()=>(this.file()?.content??'').split('\n'));
  constructor(){
    effect(()=>{this.fileId();this.tool.set('flashcards');this.pageContext.set({page:0,total:0});this.returnToFile();});
    effect(()=>{const id=this.fileId();const f=this.materials.files().find(f=>f.id===id);if(f&&!this.loaded.has(id)){this.loaded.add(id);this.selectedMode.set(f.processing?.task==='summary'?'shallow':f.processing?.mode??'shallow');this.requestedCount.set(f.processing?.requestedQuestions||60);this.details.reset({name:f.name,description:f.description??''});this.content.setValue(f.content??'');if(f.kind==='pdf'&&['Slides','Scripts'].includes(f.category))void this.loadMcq();}});
  }
  private readonly loaded=new Set<string>();
  chooseTool(tool:'flashcards'|'mcq'|'chat'):void{this.tool.set(tool);this.returnToFile();}
  selectCard(id:string):void{this.selectedCard.set(id);this.revealed.set(false);requestAnimationFrame(()=>this.stage()?.nativeElement.scrollIntoView({block:'nearest'}));}
  returnToFile():void{this.selectedCard.set(null);this.mcqSession.set(null);this.mcqFeedback.set(null);this.selectedOptions.set(new Set());this.revealed.set(false);}
  surfaceClick(event:MouseEvent):void{const target=event.target;if(target instanceof Element&&!target.closest('.flashcard-stage, .flashcard-choice, .mcq-stage, .mcq-complete, .flashcard-panel'))this.returnToFile();}
  escape(event:Event):void{if(this.selectedCard()||this.mcqSession()){event.preventDefault();event.stopPropagation();this.returnToFile();}}
  async saveDetails():Promise<void>{const value=this.details.getRawValue();if(this.kind()==='pdf'&&value.name===this.file()?.name)return;this.saving.set(true);this.error.set('');const ok=await this.materials.update(this.fileId(),this.kind()==='pdf'?{name:value.name}:value);this.saving.set(false);if(ok){this.details.controls.name.setValue(this.file()!.name);this.notice.set('File details saved.');}else this.error.set(this.materials.error());}
  async generate():Promise<void>{if(!this.validCount()||!this.allowsCards()||this.generating())return;this.error.set('');this.returnToFile();await this.materials.process(this.fileId(),false,this.selectedMode(),this.requestedCount()!,'flashcards');}
  async summarize():Promise<void>{this.error.set('');await this.materials.process(this.fileId(),false,'deep',undefined,'summary');}
  async addCard():Promise<void>{const value=this.cardForm.getRawValue();if(!value.question.trim()||!value.answer.trim()){this.error.set('Enter a question and an answer.');return;}if(await this.materials.appendCards(this.fileId(),[{question:value.question.trim(),answer:value.answer.trim(),demo:false}])){this.cardForm.reset();this.addingCard.set(false);this.error.set('');}else this.error.set(this.materials.error());}
  async saveContent():Promise<void>{if(await this.materials.update(this.fileId(),{content:this.content.value})){this.editing.set(false);this.notice.set('File content saved.');}else this.error.set(this.materials.error());}
  cancelContent():void{this.content.setValue(this.file()?.content??'');this.editing.set(false);}
  async moveDeck(parentId:string|null):Promise<void>{if(!await this.materials.update(this.fileId(),{parentId}))this.error.set(this.materials.error());else this.notice.set('Deck moved. Learning progress is preserved.');}
  heading(line:string):number{return /^(#{1,3}) /.exec(line)?.[1].length??0;}
  text(line:string):string{return line.replace(/^#{1,3} /,'').replace(/^- /,'• ');}
  async loadMcq():Promise<void>{this.mcqLoading.set(true);const sets=await this.mcq.sets(this.fileId());this.mcqSets.set(sets);this.mcqLoading.set(false);const active=sets.find(set=>set.activeSessionId);if(active?.activeSessionId&&!this.mcqSession()){const session=await this.mcq.session(active.activeSessionId);if(session)this.mcqSession.set(session);}}
  async generateMcq(action:'initial'|'additional'|'regenerate',set?:McqSet):Promise<void>{
    if(this.mcqBusy()||!this.validMcqCount())return;this.mcqBusy.set(true);const created=await this.mcq.generate(this.fileId(),this.selectedMode(),action,set?.id,this.requestedMcqCount());
    if(created)this.mcqSets.update(values=>[created,...values]);this.mcqBusy.set(false);if(created)this.pollMcq();
  }
  async retryMcq(set:McqSet):Promise<void>{if(this.mcqBusy())return;this.mcqBusy.set(true);await this.mcq.retry(set.id);this.mcqBusy.set(false);await this.loadMcq();this.pollMcq();}
  private pollMcq():void{setTimeout(async()=>{await this.loadMcq();if(this.mcqSets().some(s=>s.status==='queued'||s.status==='running'))this.pollMcq();},1500);}
  async startMcq(set:McqSet):Promise<void>{const session=await this.mcq.start(set.id);if(session){this.mcqSession.set(session);this.mcqFeedback.set(null);this.selectedOptions.set(new Set());requestAnimationFrame(()=>this.stage()?.nativeElement.scrollIntoView({block:'nearest'}));}}
  toggleOption(id:string,checked:boolean):void{const question=this.currentMcq();if(!question||this.mcqFeedback())return;const next=new Set(question.selectionMode==='single'?[]:this.selectedOptions());if(checked)next.add(id);else next.delete(id);this.selectedOptions.set(next);}
  async checkMcq():Promise<void>{const session=this.mcqSession(),question=this.currentMcq();if(!session||!question||!this.selectedOptions().size)return;const result=await this.mcq.answer(session.id,question.id,[...this.selectedOptions()]);if(result){this.mcqFeedback.set(result);this.mcqSession.set(result.session);}}
  nextMcq():void{this.mcqFeedback.set(null);this.selectedOptions.set(new Set());}
}
