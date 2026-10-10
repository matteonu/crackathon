import { Component, ElementRef, computed, effect, input, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { LoadingDotsComponent } from '../shared/loading-dots.component';
import { contextPages } from '../models/pdf-context';

interface ChatTurn {id:string;question:string;answer:string;page:number;pages:number[];searchedDocument:boolean;}
interface ChatState {index:{status:string;error:string|null};turns:ChatTurn[];}

@Component({selector:'app-document-chat',standalone:true,imports:[FormsModule,LoadingDotsComponent],template:`
  <div class="document-chat">
    <div class="chat-context" aria-live="polite">
      <strong>{{page()?'Viewing page '+page()+' of '+totalPages():'Loading page context…'}}</strong>
      <span>{{pages().length?'Context: '+pageLabel(pages())+' · Searches this document if needed.':'Open the PDF to ask a question.'}}</span>
    </div>
    @if(indexStatus()==='error'){
      <p class="chat-index-note">{{indexError()}} <button type="button" class="text-button" (click)="retryIndex()">Retry indexing</button></p>
    }@else if(indexStatus()==='queued'||indexStatus()==='indexing'){
      <p class="chat-index-note"><app-loading-dots label="Preparing document search" /> You can already ask about the visible pages.</p>
    }
    <div #feed class="chat-messages" tabindex="0" role="log" aria-label="Document conversation" aria-live="polite">
      @for(turn of turns();track turn.id){
        <div class="chat-message question"><span class="eyebrow">YOU · PAGE {{turn.page}}</span><p>{{turn.question}}</p></div>
        <div class="chat-message answer"><span class="eyebrow">STUDY ASSISTANT</span><p>{{turn.answer}}</p><small>Context: {{pageLabel(turn.pages)}}{{turn.searchedDocument?' · Searched this document':''}}</small></div>
      }@empty{
        @if(!loading()&&!pending()){
          <p class="chat-empty">Ready when you are</p>
        }
      }
      @if(loading()){<p class="field-hint"><app-loading-dots label="Loading conversation" /></p>}
      @if(pending();as pending){<div class="chat-message question"><span class="eyebrow">YOU · PAGE {{pending.page}}</span><p>{{pending.question}}</p></div><p class="field-hint" role="status"><app-loading-dots label="Thinking" /></p>}
    </div>
    @if(error()){<p class="form-error" role="alert">{{error()}}</p>}
    <form class="chat-composer" (ngSubmit)="send()">
      <label class="sr-only" for="document-question">Ask about this PDF</label>
      <textarea id="document-question" name="question" rows="3" maxlength="4000" placeholder="Ask about this page…" [ngModel]="draft()" (ngModelChange)="draft.set($event)" [disabled]="!!pending()||loading()" (keydown)="composerKey($event)"></textarea>
      <div><small>Enter to send · Shift+Enter for a new line</small><button type="submit" class="button primary" [disabled]="!canSend()">Send</button></div>
    </form>
  </div>
`})
export class DocumentChatComponent {
  readonly documentId=input.required<string>();readonly page=input.required<number>();readonly totalPages=input.required<number>();
  readonly pages=computed(()=>contextPages(this.page(),this.totalPages()));
  readonly turns=signal<ChatTurn[]>([]);readonly draft=signal('');readonly error=signal('');readonly loading=signal(true);
  readonly indexStatus=signal('');readonly indexError=signal('');
  readonly pending=signal<{question:string;page:number}|null>(null);
  readonly canSend=computed(()=>!!this.draft().trim()&&this.draft().trim().length<=4000&&this.pages().length>0&&!this.pending()&&!this.loading());
  readonly feed=viewChild<ElementRef<HTMLElement>>('feed');
  private controller=new AbortController();
  private retry:{question:string;page:number;requestId:string}|null=null;
  private reload:()=>Promise<void>=async()=>{};
  constructor(){
    effect(onCleanup=>{
      const id=this.documentId();const controller=new AbortController();this.controller=controller;
      let timer:ReturnType<typeof setTimeout>|undefined;
      this.turns.set([]);this.pending.set(null);this.draft.set('');this.error.set('');this.loading.set(true);this.indexStatus.set('');this.retry=null;
      const load=async()=>{
        clearTimeout(timer);
        try{
          const state=await this.request<ChatState>(id,'',{},controller.signal);
          if(controller.signal.aborted)return;
          // Polls update index status; preserve turns received after this fetch began.
          if(this.loading())this.turns.set(state.turns);
          this.indexStatus.set(state.index.status);this.indexError.set(state.index.error??'');
          if(['queued','indexing'].includes(state.index.status))timer=setTimeout(()=>void load(),2500);
        }catch(e){if(!controller.signal.aborted)this.error.set(e instanceof Error?e.message:'Could not load chat.');}
        finally{if(!controller.signal.aborted)this.loading.set(false);}
      };
      this.reload=load;void load();
      onCleanup(()=>{controller.abort();clearTimeout(timer);});
    });
    effect(onCleanup=>{
      this.turns();this.pending();this.loading();
      const frame=requestAnimationFrame(()=>{const feed=this.feed()?.nativeElement;if(feed)feed.scrollTop=feed.scrollHeight;});
      onCleanup(()=>cancelAnimationFrame(frame));
    });
  }
  pageLabel(pages:number[]):string {return pages.length===1?'page '+pages[0]:'pages '+pages[0]+'–'+pages.at(-1);}
  composerKey(event:KeyboardEvent):void {if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();void this.send();}}
  async send():Promise<void>{
    if(!this.canSend())return;
    const question=this.draft().trim(),page=this.page(),id=this.documentId(),signal=this.controller.signal;
    const requestId=this.retry?.question===question&&this.retry.page===page?this.retry.requestId:crypto.randomUUID();
    this.retry={question,page,requestId};this.pending.set({question,page});this.draft.set('');this.error.set('');
    try{
      const turn=await this.request<ChatTurn>(id,'',{method:'POST',body:JSON.stringify({question,page,requestId})},signal);
      if(signal.aborted)return;
      this.turns.update(turns=>turns.some(t=>t.id===turn.id)?turns:[...turns,turn]);this.retry=null;
    }catch(e){if(!signal.aborted){this.error.set(e instanceof Error?e.message:'Could not send question.');this.draft.set(question);}}
    finally{if(!signal.aborted)this.pending.set(null);}
  }
  async retryIndex():Promise<void>{
    const signal=this.controller.signal;
    try{await this.request(this.documentId(),'/index',{method:'POST'},signal);if(!signal.aborted){this.error.set('');await this.reload();}}
    catch(e){if(!signal.aborted)this.error.set(e instanceof Error?e.message:'Could not retry indexing.');}
  }
  private async request<T>(id:string,suffix:string,options:RequestInit,signal:AbortSignal):Promise<T>{
    const response=await fetch('/api/learning/documents/'+encodeURIComponent(id)+'/chat'+suffix,{...options,signal,headers:{'Content-Type':'application/json'}});
    const body=await response.json().catch(()=>({error:'The chat service is unavailable. Try again.'}));
    if(!response.ok)throw new Error(body.error??'The chat service is unavailable. Try again.');
    return body as T;
  }
}
