import { Injectable, signal } from '@angular/core';
import { Material, MaterialCategory, MaterialKind, Flashcard, normalizeMaterial, materialKind, materialName, validParent } from '../models/material';

type MaterialPatch=Partial<Pick<Material,'category'|'marker'|'outputs'|'name'|'description'|'parentId'|'content'>>;
/** Browser-local files, folders, and cards. No server requests. */
@Injectable({providedIn:'root'})
export class MaterialStore {
  readonly files=signal<Material[]>([]);readonly loading=signal(true);readonly error=signal('');readonly busy=signal(false);
  private database:Promise<IDBDatabase>;private mutations:Promise<unknown>=Promise.resolve();
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
    });this.files.set(values.map(normalizeMaterial));}
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
  async add(subjectId:string,files:File[],category:MaterialCategory,parentId:string|null=null):Promise<void>{
    if(this.loading()||this.busy())return;this.busy.set(true);this.error.set('');
    try{await this.queue(async()=>{
      this.assertParent(subjectId,parentId);const pending:Material[]=[];
      for(const file of files){
        if(file.size>50*1024*1024)throw new Error(`${file.name} exceeds the 50 MB file limit.`);
        if(!/\.pdf$/i.test(file.name)||!(await file.slice(0,1024).text()).includes('%PDF-'))throw new Error(`${file.name} is not a PDF.`);
        let name=file.name;let suffix=2;
        const used=(candidate:string)=>[...this.files(),...pending].some(f=>f.subjectId===subjectId&&(f.parentId??null)===parentId&&f.name.toLowerCase()===candidate.toLowerCase());
        while(used(name))name=file.name.replace(/\.pdf$/i,` (${suffix++}).pdf`);
        pending.push({id:crypto.randomUUID(),subjectId,parentId,kind:'pdf',name,description:'',size:file.size,category,marker:'To read',blob:file,added:Date.now()});
      }
      await this.write(pending);this.files.update(values=>[...values,...pending]);
    });}catch(e){this.error.set(e instanceof Error?e.message:'Could not save PDFs. Browser storage may be full.');}finally{this.busy.set(false);}
  }
  update(id:string,patch:MaterialPatch):Promise<boolean>{return this.queue(async()=>{
    const file=this.files().find(f=>f.id===id);if(!file)return false;
    try{
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
