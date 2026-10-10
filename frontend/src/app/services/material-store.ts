import { Injectable, inject, signal } from '@angular/core';
import { Material, MaterialCategory, MaterialKind, Flashcard, LearningMode, normalizeMaterial, materialKind, materialName, validParent } from '../models/material';
import { learningPatch } from '../models/learning';
import { LearningPipelineService } from './learning-pipeline.service';

type MaterialPatch=Partial<Pick<Material,'category'|'marker'|'outputs'|'name'|'description'|'parentId'|'content'|'processing'>>;
/** Local file library, with PDF summaries and cards read from Python's saved JSON. */
@Injectable({providedIn:'root'})
export class MaterialStore {
  readonly files=signal<Material[]>([]);readonly loading=signal(true);readonly error=signal('');readonly busy=signal(false);
  private database:Promise<IDBDatabase>;private mutations:Promise<unknown>=Promise.resolve();
  private readonly pipeline=inject(LearningPipelineService);private readonly activeJobs=new Set<string>();
  constructor(){
    this.database=new Promise((resolve,reject)=>{
      const request=indexedDB.open('studyphase-materials',1);
      request.onupgradeneeded=()=>request.result.createObjectStore('files',{keyPath:'id'});
      request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
      request.onblocked=()=>reject(new Error('Close other Studyphase tabs and try again.'));
    });void this.load();
  }
  private async load():Promise<void>{
    try{const db=await this.database;const values=await new Promise<Material[]>((resolve,reject)=>{
      const request=db.transaction('files').objectStore('files').getAll();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
    });this.files.set(values.map(normalizeMaterial));
      for(const file of this.files())if(materialKind(file)==='pdf'&&file.processing)void this.process(file.id,true);
    }
    catch{this.error.set('Local storage is unavailable. Enable browser storage and reload.');}finally{this.loading.set(false);}
  }
  private async write(files:Material[]):Promise<void>{
    const db=await this.database;await new Promise<void>((resolve,reject)=>{
      const transaction=db.transaction('files','readwrite');for(const file of files)transaction.objectStore('files').put(file);
      transaction.oncomplete=()=>resolve();transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error);
    });
  }
  private assertParent(subjectId:string,parentId:string|null,id?:string):void {
    if(!validParent(this.files(),subjectId,parentId,id))throw new Error('Choose a folder in this subject. A folder cannot contain itself.');
  }
  private assertUnique(file:Material):void {
    if(this.files().some(f=>f.id!==file.id&&f.subjectId===file.subjectId&&(f.parentId??null)===(file.parentId??null)&&f.name.toLowerCase()===file.name.toLowerCase()))throw new Error('That name already exists in this folder.');
  }
  private queue<T>(work:()=>Promise<T>):Promise<T>{const operation=this.mutations.then(work);this.mutations=operation.catch(()=>undefined);return operation;}
  async create(subjectId:string,parentId:string|null,kind:Exclude<MaterialKind,'pdf'>,name:string):Promise<Material>{
    return this.queue(async()=>{
      this.assertParent(subjectId,parentId);
      const content=kind==='md'?'# New note\n\nStart writing here.\n':'';
      const blob=new Blob([content],{type:'text/plain'});
      const file:Material={id:crypto.randomUUID(),subjectId,parentId,kind,name:materialName(name,kind),description:'',content,blob,size:blob.size,category:'Notes',marker:'To read',added:Date.now()};
      this.assertUnique(file);await this.write([file]);this.files.update(values=>[...values,file]);this.error.set('');return file;
    });
  }
  async add(subjectId:string,files:File[],category:MaterialCategory,parentId:string|null=null,mode:LearningMode='shallow',requestedQuestions=60):Promise<void>{
    if(this.loading()||this.busy())return;this.busy.set(true);this.error.set('');
    try{const added=await this.queue(async()=>{
      if(!Number.isInteger(requestedQuestions)||requestedQuestions<5||requestedQuestions>300)throw new Error('Enter a whole number of flashcards from 5 to 300.');
      this.assertParent(subjectId,parentId);const pending:Material[]=[];
      for(const file of files){
        if(file.size>=50_000_000)throw new Error(`${file.name} must be smaller than 50 MB.`);
        if(!/\.pdf$/i.test(file.name)||!(await file.slice(0,1024).text()).includes('%PDF-'))throw new Error(`${file.name} is not a PDF.`);
        let name=file.name;let suffix=2;
        const used=(candidate:string)=>[...this.files(),...pending].some(f=>f.subjectId===subjectId&&(f.parentId??null)===parentId&&f.name.toLowerCase()===candidate.toLowerCase());
        while(used(name))name=file.name.replace(/\.pdf$/i,` (${suffix++}).pdf`);
        pending.push({id:crypto.randomUUID(),subjectId,parentId,kind:'pdf',name,description:'',size:file.size,category,marker:'To read',blob:file,added:Date.now(),processing:{status:'queued',mode,requestedQuestions}});
      }
      await this.write(pending);this.files.update(values=>[...values,...pending]);return pending;
    });for(const file of added)void this.process(file.id);}catch(e){this.error.set(e instanceof Error?e.message:'Could not save PDFs. Browser storage may be full.');}finally{this.busy.set(false);}
  }
  remove(id:string):Promise<boolean>{return this.queue(async()=>{
    const file=this.files().find(f=>f.id===id);if(!file||materialKind(file)!=='pdf')return false;
    try{
      if(file.processing)await this.pipeline.remove(id);
      const db=await this.database;await new Promise<void>((resolve,reject)=>{
        const transaction=db.transaction('files','readwrite');transaction.objectStore('files').delete(id);
        transaction.oncomplete=()=>resolve();transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error);
      });
      this.files.update(files=>files.filter(f=>f.id!==id));this.error.set('');return true;
    }catch(e){this.error.set(e instanceof Error?e.message:'Could not delete this PDF. Please retry.');return false;}
  });}
  async process(id:string,resume=false,selectedMode?:LearningMode):Promise<void>{
    const file=this.files().find(f=>f.id===id);if(!file||materialKind(file)!=='pdf'||this.activeJobs.has(id))return;
    const mode=selectedMode??file.processing?.mode??'shallow';
    const requestedQuestions=file.processing?.requestedQuestions??60;
    this.activeJobs.add(id);
    try{
      if(!resume&&!await this.update(id,current=>(current.processing?.mode??'shallow')===mode?{processing:{status:'queued',mode,requestedQuestions}}:learningPatch(current,{id,mode,requested_questions:requestedQuestions,status:'queued',documents:[]})))throw new Error(this.error());
      await this.pipeline.process(file,async result=>{
        if(!await this.update(id,current=>learningPatch(current,result)))throw new Error(this.error()||'Could not save generated results.');
      },resume,mode);
    }catch(e){await this.update(id,{processing:{status:'error',mode,requestedQuestions,error:e instanceof Error?e.message:'Processing failed. Retry this file.'}});}
    finally{this.activeJobs.delete(id);}
  }
  update(id:string,change:MaterialPatch|((file:Material)=>MaterialPatch)):Promise<boolean>{return this.queue(async()=>{
    const file=this.files().find(f=>f.id===id);if(!file)return false;
    try{
      const patch=typeof change==='function'?change(file):change;
      const next={...file,...patch,outputs:{...file.outputs,...patch.outputs}};
      next.name=materialName(next.name,materialKind(next));this.assertParent(next.subjectId,next.parentId??null,id);this.assertUnique(next);
      if(patch.content!==undefined){if(!['md','txt'].includes(materialKind(file)))throw new Error('Only text files can be edited.');next.blob=new Blob([patch.content],{type:'text/plain'});next.size=next.blob.size;}
      await this.write([next]);this.files.update(values=>values.map(f=>f.id===id?next:f));this.error.set('');return true;
    }catch(e){this.error.set(e instanceof Error?e.message:'Could not save changes. Please retry.');return false;}
  });}
  appendCards(id:string,cards:Flashcard[]):Promise<boolean>{return this.queue(async()=>{
    const file=this.files().find(f=>f.id===id);if(!file||materialKind(file)==='folder')return false;
    const next={...file,outputs:{...file.outputs,flashcards:{cards:[...file.outputs?.flashcards?.cards??[],...cards.map(c=>({...c,id:crypto.randomUUID()}))]}}};
    try{await this.write([next]);this.files.update(values=>values.map(f=>f.id===id?next:f));return true;}
    catch{this.error.set('Could not save flashcards. Please retry.');return false;}
  });}
}
