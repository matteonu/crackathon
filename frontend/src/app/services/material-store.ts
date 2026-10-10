import { Injectable, signal } from '@angular/core';
import { Material, MaterialCategory, MaterialMarker } from '../models/material';

/** Local PDF library; replace this service to connect remote storage later. */
@Injectable({providedIn:'root'})
export class MaterialStore {
  readonly files=signal<Material[]>([]);
  readonly loading=signal(true); readonly error=signal(''); readonly busy=signal(false);
  private database:Promise<IDBDatabase>;
  private mutations:Promise<unknown>=Promise.resolve();
  constructor(){
    this.database=new Promise((resolve,reject)=>{
      const request=indexedDB.open('studyphase-materials',1);
      request.onupgradeneeded=()=>request.result.createObjectStore('files',{keyPath:'id'});
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
      request.onblocked=()=>reject(new Error('Close other Studyphase tabs and try again.'));
    });
    void this.load();
  }
  private async load():Promise<void>{
    try{const db=await this.database;const values=await new Promise<Material[]>((resolve,reject)=>{
      const request=db.transaction('files').objectStore('files').getAll();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
    });this.files.set(values);}catch{this.error.set('Local PDF storage is unavailable. Enable browser storage and reload to add materials.');}
    finally{this.loading.set(false);}
  }
  private async write(files:Material[],remove?:string):Promise<void>{
    const db=await this.database;
    await new Promise<void>((resolve,reject)=>{
      const transaction=db.transaction('files','readwrite');const store=transaction.objectStore('files');
      if(remove)store.delete(remove);for(const file of files)store.put(file);
      transaction.oncomplete=()=>resolve();transaction.onerror=()=>reject(transaction.error);transaction.onabort=()=>reject(transaction.error);
    });
  }
  async add(subjectId:string,files:File[],category:MaterialCategory):Promise<void>{
    if(this.loading() || this.busy())return;
    this.busy.set(true);this.error.set('');
    try{
      const pending:Material[]=[];
      for(const file of files){
        if(!/\.pdf$/i.test(file.name) || !(await file.slice(0,1024).text()).includes('%PDF-'))throw new Error(`${file.name} is not a PDF.`);
        if(file.size>50*1024*1024)throw new Error(`${file.name} exceeds the 50 MB file limit.`);
        pending.push({id:crypto.randomUUID(),subjectId,name:file.name,size:file.size,category,marker:'To read',blob:file,added:Date.now()});
      }
      await this.write(pending);this.files.update(values=>[...values,...pending]);
    }catch(e){this.error.set(e instanceof Error?e.message:'Could not save PDFs. Browser storage may be full.');}
    finally{this.busy.set(false);}
  }
  update(id:string,patch:{category?:MaterialCategory;marker?:MaterialMarker;outputs?:Material['outputs']}):Promise<boolean>{
    const operation=this.mutations.then(async()=>{
      const file=this.files().find(f=>f.id===id);if(!file)return false;
      const next={...file,...patch,outputs:{...file.outputs,...patch.outputs}};
      try{await this.write([next]);this.files.update(values=>values.map(f=>f.id===id?next:f));this.error.set('');return true;}
      catch{this.error.set('Could not save this file’s changes. Please retry.');return false;}
    });
    this.mutations=operation;return operation;
  }
  remove(id:string):Promise<void>{
    const operation=this.mutations.then(async()=>{
      try{await this.write([],id);this.files.update(files=>files.filter(f=>f.id!==id));this.error.set('');}
      catch{this.error.set('Could not remove this PDF. Please retry.');}
    });
    this.mutations=operation;return operation;
  }
}
