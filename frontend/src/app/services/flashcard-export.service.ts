import { Injectable } from '@angular/core';
import type { FolderCard } from '../models/material';
@Injectable({providedIn:'root'})
export class FlashcardExportService {
  async export(cards:readonly FolderCard[],name:string,key:string):Promise<void>{
    const [{default:initSqlJs},{buildApkg}]=await Promise.all([import('sql.js'),import('../models/apkg')]);
    const SQL=await initSqlJs({locateFile:file=>new URL('assets/sqljs/'+file,document.baseURI).href});
    const bytes=await buildApkg(SQL,cards,name,key);
    const url=URL.createObjectURL(new Blob([new Uint8Array(bytes)],{type:'application/octet-stream'}));
    const link=document.createElement('a');link.href=url;link.download=(name.replace(/[<>:"/\\|?*]/g,'-')||'Materials')+'.apkg';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
}
