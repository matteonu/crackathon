import { Injectable, signal } from '@angular/core';
import type { Rating, RecallAnalytics } from '../models/recall';
export type { Rating, RecallAnalytics } from '../models/recall';

export interface PracticeScope {subjectId?:string;folderId?:string|null;deckId?:string|null;}
export interface PracticeCard {
  id:string;deckId:string;version:number;question:string;answer:string;demo:boolean;
  fileId:string;fileName:string;predictions:Record<Rating,{due:string;seconds:number}>;
}
export interface PracticeSession {cards:PracticeCard[];serverNow:string;nextDue:string|null;dueCount:number;}
export class SchedulerError extends Error {constructor(message:string,readonly status:number){super(message);}}

@Injectable({providedIn:'root'})
export class SchedulerService {
  readonly analytics=signal<RecallAnalytics[]>([]);readonly analyticsError=signal('');
  private url(path:string,scope:PracticeScope):URL {
    const url=new URL('/api/practice/'+path,document.baseURI);
    if(scope.subjectId)url.searchParams.set('subject',scope.subjectId);
    if(scope.folderId)url.searchParams.set('folder',scope.folderId);
    if(scope.deckId)url.searchParams.set('deck',scope.deckId);
    return url;
  }
  private async request<T>(url:URL|string,init?:RequestInit):Promise<T>{
    let response:Response;
    try{response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(30000),...init});}
    catch{throw new SchedulerError('Cannot reach the server. Retry when connected.',0);}
    const data=await response.json();
    if(!response.ok)throw new SchedulerError(data.error??'Could not update learning progress.',response.status);
    return data as T;
  }
  session(scope:PracticeScope,limit:number,newCardLimit:number):Promise<PracticeSession>{
    const url=this.url('session',scope);url.searchParams.set('limit',String(limit));url.searchParams.set('newCardLimit',String(newCardLimit));
    return this.request(url);
  }
  statistics(scope:PracticeScope):Promise<RecallAnalytics[]>{return this.request(this.url('analytics',scope));}
  async review(card:PracticeCard,rating:Rating,responseSeconds:number):Promise<void>{
    await this.request('/api/practice/review',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({deckId:card.deckId,cardId:card.id,version:card.version,rating,responseSeconds})});
    void this.refreshAnalytics();
  }
  async refreshAnalytics():Promise<void>{
    try{this.analytics.set(await this.request<RecallAnalytics[]>(this.url('analytics',{})));this.analyticsError.set('');}
    catch(e){this.analyticsError.set(e instanceof Error?e.message:'Could not load recall statistics.');}
  }
}
