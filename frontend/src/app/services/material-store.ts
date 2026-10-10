import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { Material, MaterialCategory, MaterialKind, Flashcard, LearningMode, LearningTask, CATEGORY_DOCUMENT_TYPES, descendants, canGenerateFlashcards, normalizeMaterial, materialKind, materialName, validParent } from '../models/material';
import { learningPatch } from '../models/learning';
import { LearningPipelineService } from './learning-pipeline.service';

<<<<<<< HEAD
type MaterialPatch=Partial<Pick<Material,'category'|'type'|'marker'|'outputs'|'name'|'description'|'parentId'|'content'|'processing'|'folderWeight'>>;
class MaterialRequestError extends Error {
  constructor(readonly status:number,message:string){super(message);}
}
=======
type MaterialPatch=Partial<Pick<Material,'category'|'marker'|'outputs'|'name'|'description'|'parentId'|'content'|'processing'|'folderWeight'>>;
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
/** The file library, stored on the server: metadata in SQLite, PDFs and generated JSON on disk. */
@Injectable({providedIn:'root'})
export class MaterialStore {
  readonly files=signal<Material[]>([]);readonly loading=signal(true);readonly error=signal('');readonly busy=signal(false);
  private mutations:Promise<unknown>=Promise.resolve();
  private readonly pipeline=inject(LearningPipelineService);private readonly activeJobs=new Set<string>();
  constructor(){
    void this.queue(()=>this.load());
    const refresh=()=>{void this.refresh();};
    window.addEventListener('focus',refresh);
    inject(DestroyRef).onDestroy(()=>window.removeEventListener('focus',refresh));
  }
  private async request<T>(url:string,init?:RequestInit):Promise<T>{
    let response:Response;
    try{response=await fetch(url,{cache:'no-store',...init});}
    catch{throw new Error('Cannot reach the server. Check your connection and retry.');}
    let data:unknown=null;
    try{data=await response.json();}catch{/* 204 and non-JSON errors have no body. */}
    if(!response.ok)throw new MaterialRequestError(response.status,typeof (data as {error?:unknown})?.error==='string'?(data as {error:string}).error:'The server could not save that change. Please retry.');
    return data as T;
  }
  private async load():Promise<void>{
    try{
      this.files.set((await this.request<Material[]>('/api/materials')).map(normalizeMaterial));
      for(const file of this.files())if(materialKind(file)==='pdf'&&file.processing)void this.process(file.id,true);
      this.error.set('');
    }
    catch(e){this.error.set(e instanceof Error?e.message:'Could not load your files.');}finally{this.loading.set(false);}
  }
  refresh():Promise<void>{return this.queue(async()=>{
    try{this.files.set((await this.request<Material[]>('/api/materials')).map(normalizeMaterial));}
    catch{/* A failed background refresh must not remove files or interrupt editing. */}
  });}
  private forget(id:string,removed:string[]=[]):void{
    const ids=new Set([id,...removed,...descendants(this.files(),id).map(file=>file.id)]);
    this.files.update(files=>files.filter(file=>!ids.has(file.id)));
  }
  ensureAvailable(id:string):Promise<boolean>{return this.queue(async()=>{
    try{this.store(await this.request<Material>(`/api/materials/${id}`));this.error.set('');return true;}
    catch(e){
      if(e instanceof MaterialRequestError&&e.status===404){this.forget(id);this.error.set('This item was already deleted. The list has been updated.');}
      else this.error.set(e instanceof Error?e.message:'Could not open this file. Please retry.');
      return false;
    }
  });}
  private assertParent(subjectId:string,parentId:string|null,id?:string):void {
    if(!validParent(this.files(),subjectId,parentId,id))throw new Error('Choose a folder in this subject. A folder cannot contain itself.');
  }
  async refresh():Promise<void>{this.files.set((await this.request<Material[]>('/api/materials')).map(normalizeMaterial));}
  private assertUnique(file:Material):void {
    if(this.files().some(f=>f.id!==file.id&&f.subjectId===file.subjectId&&(f.parentId??null)===(file.parentId??null)&&f.name.toLowerCase()===file.name.toLowerCase()))throw new Error('That name already exists in this folder.');
  }
  private queue<T>(work:()=>Promise<T>):Promise<T>{const operation=this.mutations.then(work);this.mutations=operation.catch(()=>undefined);return operation;}
  private store(file:Material):Material{
    const saved=normalizeMaterial(file);
    this.files.update(values=>values.some(f=>f.id===saved.id)?values.map(f=>f.id===saved.id?saved:f):[...values,saved]);
    return saved;
  }
  async create(subjectId:string,parentId:string|null,kind:Exclude<MaterialKind,'pdf'|'deck'>,name:string):Promise<Material>{
    return this.queue(async()=>{
      this.assertParent(subjectId,parentId);
      const content=kind==='md'?'# New note\n\nStart writing here.\n':'';
      const draft={id:crypto.randomUUID(),subjectId,parentId,kind,name:materialName(name,kind),content,category:'Notes' as MaterialCategory,marker:'To read' as const};
      this.assertUnique(draft as Material);
      const saved=this.store(await this.request<Material>('/api/materials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft)}));
      this.error.set('');return saved;
    });
  }
  async add(subjectId:string,files:File[],category:MaterialCategory,parentId:string|null=null):Promise<void>{
    if(this.loading()||this.busy())return;this.busy.set(true);this.error.set('');
    const added:Material[]=[];
    try{await this.queue(async()=>{
      this.assertParent(subjectId,parentId);const saved=added;
      for(const file of files){
        if(file.size>=50_000_000)throw new Error(`${file.name} must be smaller than 50 MB.`);
        if(!/\.pdf$/i.test(file.name)||!(await file.slice(0,1024).text()).includes('%PDF-'))throw new Error(`${file.name} is not a PDF.`);
        let name=file.name;let suffix=2;
        const used=(candidate:string)=>[...this.files(),...saved].some(f=>f.subjectId===subjectId&&(f.parentId??null)===parentId&&f.name.toLowerCase()===candidate.toLowerCase());
        while(used(name))name=file.name.replace(/\.pdf$/i,` (${suffix++}).pdf`);
        // The row comes first so the id exists; then the bytes are uploaded once, and
        // processing reads them from the server instead of sending them again.
        const created=await this.request<Material>('/api/materials',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({id:crypto.randomUUID(),subjectId,parentId,kind:'pdf',name,category,type:CATEGORY_DOCUMENT_TYPES[category]??null,size:file.size,processing:{status:'queued',mode:'deep',task:'summary',requestedQuestions:60}})});
        try{saved.push(this.store(await this.request<Material>(`/api/materials/${created.id}/file`,{method:'PUT',headers:{'Content-Type':'application/pdf'},body:file})));}
        catch(e){await this.request(`/api/materials/${created.id}`,{method:'DELETE'}).catch(()=>undefined);throw e;}
      }
      return saved;
    });}catch(e){this.error.set(e instanceof Error?e.message:'Could not save PDFs. Please retry.');}finally{this.busy.set(false);for(const file of added)void this.process(file.id,false,'deep',60,'summary');}
  }
  remove(id:string):Promise<boolean>{return this.queue(async()=>{
<<<<<<< HEAD
    const file=this.files().find(f=>f.id===id);if(!file)return true;
    try{
      // The response includes every row removed from this folder's subtree.
      const result=await this.request<{deleted:string[]}>(`/api/materials/${id}`,{method:'DELETE'});
      this.forget(id,result.deleted);
      // Independent decks survive source deletion with their PDF reference cleared.
      try{this.files.set((await this.request<Material[]>('/api/materials')).map(normalizeMaterial));}
      catch{/* Keep the known committed deletion if a background refresh fails. */}
      this.error.set('');return true;
    }catch(e){
      if(e instanceof MaterialRequestError&&e.status===404){this.forget(id);this.error.set('');return true;}
      // A server error or lost response can happen after the deletion committed.
      try{this.files.set((await this.request<Material[]>('/api/materials')).map(normalizeMaterial));
        if(!this.files().some(file=>file.id===id)){this.error.set('');return true;}}
      catch{/* Keep the last known list when the server cannot be reached. */}
      this.error.set(e instanceof Error?e.message:'Could not delete this item. Please retry.');return false;
    }
=======
    const file=this.files().find(f=>f.id===id);if(!file||!['pdf','deck'].includes(materialKind(file)))return false;
    try{
      // The server deletes the row, the stored PDF and every generated result together.
      await this.request(`/api/materials/${id}`,{method:'DELETE'});
      await this.refresh();this.error.set('');return true;
    }catch(e){this.error.set(e instanceof Error?e.message:'Could not delete this PDF. Please retry.');return false;}
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
  });}
  async process(id:string,resume=false,selectedMode?:LearningMode,count?:number,selectedTask?:LearningTask):Promise<void>{
    const file=this.files().find(f=>f.id===id);if(!file||materialKind(file)!=='pdf'||this.activeJobs.has(id))return;
    const mode=selectedMode??file.processing?.mode??'shallow';
    const task=selectedTask??file.processing?.task??'flashcards';
    if(task==='flashcards'&&!canGenerateFlashcards(file))return;
    const requestedQuestions=count??file.processing?.requestedQuestions??60;
    if(task==='flashcards'&&(!Number.isInteger(requestedQuestions)||requestedQuestions<5||requestedQuestions>300)){this.error.set('Enter a whole number of flashcards from 5 to 300.');return;}
    this.activeJobs.add(id);
    try{
      if(!resume&&!await this.update(id,{processing:{status:'queued',mode,task,requestedQuestions}}))throw new Error(this.error());
      await this.pipeline.process(file,async result=>{
        if(!await this.update(id,current=>learningPatch(current,result)))throw new Error(this.error()||'Could not save generated results.');
        if(result.status==='complete')await this.refresh();
<<<<<<< HEAD
      },resume,mode,task,requestedQuestions);
    }catch(e){await this.update(id,{processing:{status:'error',mode,task,requestedQuestions,error:e instanceof Error?e.message:'Processing failed. Retry this file.'}});}
=======
      },resume,mode);
    }catch(e){await this.update(id,{processing:{status:'error',mode,requestedQuestions,error:e instanceof Error?e.message:'Processing failed. Retry this file.'}});}
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
    finally{this.activeJobs.delete(id);}
  }
  update(id:string,change:MaterialPatch|((file:Material)=>MaterialPatch)):Promise<boolean>{return this.queue(async()=>{
    const file=this.files().find(f=>f.id===id);if(!file)return false;
    try{
      const patch=typeof change==='function'?change(file):change;
      const next={...file,...patch,outputs:{...file.outputs,...patch.outputs}};
      next.name=materialName(next.name,materialKind(next));this.assertParent(next.subjectId,next.parentId??null,id);this.assertUnique(next);
      if(patch.content!==undefined&&!['md','txt'].includes(materialKind(file)))throw new Error('Only text files can be edited.');
      this.store(await this.request<Material>(`/api/materials/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...patch,name:next.name,outputs:next.outputs})}));
      this.error.set('');return true;
    }catch(e){if(e instanceof MaterialRequestError&&e.status===404)this.forget(id);this.error.set(e instanceof Error?e.message:'Could not save changes. Please retry.');return false;}
  });}
  appendCards(id:string,cards:Flashcard[]):Promise<boolean>{return this.queue(async()=>{
    const file=this.files().find(f=>f.id===id);if(!file||materialKind(file)==='folder')return false;
    try{this.store(await this.request<Material>(`/api/materials/${id}/cards`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cards})}));return true;}
<<<<<<< HEAD
    catch(e){if(e instanceof MaterialRequestError&&e.status===404)this.forget(id);this.error.set(e instanceof Error?e.message:'Could not save flashcards. Please retry.');return false;}
=======
    catch(e){this.error.set(e instanceof Error?e.message:'Could not save flashcards. Please retry.');return false;}
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
  });}
}
