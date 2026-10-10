import { Injectable, signal } from '@angular/core';
import { Task, cleanTitle, movedPosition, openTasks, topPosition, validTask } from '../models/task';

type TaskPatch=Partial<Pick<Task,'title'|'notes'|'due'|'done'|'position'>>;

/** Per-subject to-do lists, stored on the server (`/api/tasks`). Same shape as MaterialStore:
 *  optimistic signal state, one queue so edits do not race, and a user-facing error. */
@Injectable({providedIn:'root'})
export class TaskStore {
  readonly tasks=signal<Task[]>([]);readonly loading=signal(true);readonly error=signal('');
  private mutations:Promise<unknown>=Promise.resolve();
  constructor(){void this.load();}
  private async request<T>(url:string,init?:RequestInit):Promise<T>{
    let response:Response;
    try{response=await fetch(url,{cache:'no-store',...init});}
    catch{throw new Error('Cannot reach the server. Check your connection and retry.');}
    let data:unknown=null;
    try{data=await response.json();}catch{/* 204 and non-JSON errors have no body. */}
    if(!response.ok)throw new Error(typeof (data as {error?:unknown})?.error==='string'?(data as {error:string}).error:'The server could not save that change. Please retry.');
    return data as T;
  }
  private json(body:unknown,method:string):RequestInit{return {method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};}
  private queue<T>(work:()=>Promise<T>):Promise<T>{const operation=this.mutations.then(work);this.mutations=operation.catch(()=>undefined);return operation;}
  private store(task:Task):Task{this.tasks.update(values=>values.some(t=>t.id===task.id)?values.map(t=>t.id===task.id?task:t):[...values,task]);return task;}
  private async load():Promise<void>{
    try{this.tasks.set((await this.request<unknown[]>('/api/tasks')).filter(validTask));this.error.set('');}
    catch(e){this.error.set(e instanceof Error?e.message:'Could not load your tasks.');}
    finally{this.loading.set(false);}
  }
  /** Adds a task at the top of the subject's list. Returns it, or null with `error` set. */
  add(subjectId:string,title:string,due:string|null=null):Promise<Task|null>{return this.queue(async()=>{
    const clean=cleanTitle(title);
    if(!clean){this.error.set('Give the task a title.');return null;}
    const draft={id:crypto.randomUUID(),subjectId,title:clean,notes:'',due,position:topPosition(this.tasks(),subjectId)};
    try{const saved=this.store(await this.request<Task>('/api/tasks',this.json(draft,'POST')));this.error.set('');return saved;}
    catch(e){this.error.set(e instanceof Error?e.message:'Could not add the task. Please retry.');return null;}
  });}
  update(id:string,patch:TaskPatch):Promise<boolean>{return this.queue(async()=>{
    const task=this.tasks().find(t=>t.id===id);if(!task)return false;
    const body:TaskPatch={...patch};
    if(body.title!==undefined){body.title=cleanTitle(body.title);if(!body.title){this.error.set('Give the task a title.');return false;}}
    if(body.notes!==undefined)body.notes=body.notes.trim();
    try{this.store(await this.request<Task>(`/api/tasks/${id}`,this.json(body,'PATCH')));this.error.set('');return true;}
    catch(e){this.error.set(e instanceof Error?e.message:'Could not save the task. Please retry.');return false;}
  });}
  toggle(id:string):Promise<boolean>{const task=this.tasks().find(t=>t.id===id);return task?this.update(id,{done:!task.done}):Promise.resolve(false);}
  /** Moves an open task one step up or down within its subject. */
  move(id:string,direction:-1|1):Promise<boolean>{
    const task=this.tasks().find(t=>t.id===id);if(!task||task.done)return Promise.resolve(false);
    const position=movedPosition(openTasks(this.tasks(),task.subjectId),id,direction);
    return position===null?Promise.resolve(false):this.update(id,{position});
  }
  remove(id:string):Promise<boolean>{return this.queue(async()=>{
    if(!this.tasks().some(t=>t.id===id))return false;
    try{await this.request(`/api/tasks/${id}`,{method:'DELETE'});this.tasks.update(values=>values.filter(t=>t.id!==id));this.error.set('');return true;}
    catch(e){this.error.set(e instanceof Error?e.message:'Could not delete the task. Please retry.');return false;}
  });}
  clearCompleted(subjectId:string):Promise<boolean>{return this.queue(async()=>{
    try{
      await this.request(`/api/tasks/completed?subject=${encodeURIComponent(subjectId)}`,{method:'DELETE'});
      this.tasks.update(values=>values.filter(t=>!(t.subjectId===subjectId&&t.done)));this.error.set('');return true;
    }catch(e){this.error.set(e instanceof Error?e.message:'Could not clear completed tasks. Please retry.');return false;}
  });}
}
