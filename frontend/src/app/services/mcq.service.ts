import { Injectable, signal } from '@angular/core';
import { LearningMode } from '../models/material';
import { McqAnswerResult, McqSession, McqSet } from '../models/mcq';

@Injectable({providedIn:'root'})
export class McqService {
  readonly error=signal('');
  private async request<T>(url:string,init?:RequestInit):Promise<T>{
    let response:Response;
    try{response=await fetch(url,{cache:'no-store',...init});}catch{throw new Error('Cannot reach the server. Check your connection and retry.');}
    let data:unknown={};try{data=await response.json();}catch{/* handled below */}
    if(!response.ok)throw new Error(typeof (data as {error?:unknown}).error==='string'?(data as {error:string}).error:'The server could not complete that request.');
    return data as T;
  }
  async sets(documentId:string):Promise<McqSet[]>{return this.run(()=>this.request(`/api/learning/documents/${documentId}/mcq-sets`),[]);}
  async detail(setId:string):Promise<McqSet|null>{return this.run(()=>this.request(`/api/learning/mcq-sets/${setId}`),null);}
  async generate(documentId:string,mode:LearningMode,action:'initial'|'additional'|'regenerate',setId?:string,questionCount?:number|null):Promise<McqSet|null>{
    return this.run(()=>this.request(`/api/learning/documents/${documentId}/mcq-sets`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mode,action,setId,questionCount:questionCount??null,idempotencyKey:crypto.randomUUID()})}),null);
  }
  async retry(setId:string):Promise<McqSet|null>{return this.run(()=>this.request(`/api/learning/mcq-sets/${setId}/retry`,{method:'POST'}),null);}
  async sessions(setId:string):Promise<McqSession[]>{return this.run(()=>this.request(`/api/learning/mcq-sets/${setId}/sessions`),[]);}
  async start(setId:string):Promise<McqSession|null>{return this.run(()=>this.request(`/api/learning/mcq-sets/${setId}/sessions`,{method:'POST'}),null);}
  async session(id:string):Promise<McqSession|null>{return this.run(()=>this.request(`/api/learning/mcq-sessions/${id}`),null);}
  async answer(sessionId:string,questionId:string,selectedOptionIds:string[]):Promise<McqAnswerResult|null>{
    return this.run(()=>this.request(`/api/learning/mcq-sessions/${sessionId}/answers`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({questionId,selectedOptionIds})}),null);
  }
  private async run<T>(work:()=>Promise<T>,fallback:T):Promise<T>{try{const value=await work();this.error.set('');return value;}catch(e){this.error.set(e instanceof Error?e.message:'The request failed.');return fallback;}}
}
