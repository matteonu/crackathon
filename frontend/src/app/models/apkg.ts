import type { FolderCard } from './material';
import type { SqlJsStatic } from 'sql.js';

// Anki's legacy .apkg interchange: collection.anki2 (SQLite) + media manifest in ZIP.
// Format reference: https://github.com/kerrickstaley/genanki/tree/main/genanki
const schema=`
CREATE TABLE col(id integer primary key,crt integer not null,mod integer not null,scm integer not null,ver integer not null,dty integer not null,usn integer not null,ls integer not null,conf text not null,models text not null,decks text not null,dconf text not null,tags text not null);
CREATE TABLE notes(id integer primary key,guid text not null,mid integer not null,mod integer not null,usn integer not null,tags text not null,flds text not null,sfld integer not null,csum integer not null,flags integer not null,data text not null);
CREATE TABLE cards(id integer primary key,nid integer not null,did integer not null,ord integer not null,mod integer not null,usn integer not null,type integer not null,queue integer not null,due integer not null,ivl integer not null,factor integer not null,reps integer not null,lapses integer not null,left integer not null,odue integer not null,odid integer not null,flags integer not null,data text not null);
CREATE TABLE revlog(id integer primary key,cid integer not null,usn integer not null,ease integer not null,ivl integer not null,lastIvl integer not null,factor integer not null,time integer not null,type integer not null);
CREATE TABLE graves(usn integer not null,oid integer not null,type integer not null);
CREATE INDEX ix_notes_usn ON notes(usn); CREATE INDEX ix_cards_usn ON cards(usn); CREATE INDEX ix_cards_nid ON cards(nid); CREATE INDEX ix_notes_csum ON notes(csum); CREATE INDEX ix_cards_sched ON cards(did,queue,due); CREATE INDEX ix_revlog_usn ON revlog(usn); CREATE INDEX ix_revlog_cid ON revlog(cid);`;
const html=(text:string)=>text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/\n/g,'<br>');
async function identity(text:string):Promise<{id:number;guid:string}>{
  const hash=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)));
  const hex=Array.from(hash,b=>b.toString(16).padStart(2,'0')).join('');return {id:parseInt(hex.slice(0,12),16)||2,guid:hex.slice(0,20)};
}
export async function buildApkg(SQL:SqlJsStatic,cards:readonly FolderCard[],name:string,key:string,baseUrl?:string):Promise<Uint8Array>{
  if(!cards.length)throw new Error('This folder has no flashcards yet.');
  const {zipSync,strToU8}=await import('fflate');const db=new SQL.Database();
  const now=Date.now(),seconds=Math.floor(now/1000),deckId=(await identity('deck:'+key)).id,modelId=1740000000001;
  const deck=(id:number,title:string)=>({id,name:title,desc:'Exported from Studyhub',mod:seconds,usn:-1,dyn:0,conf:1,collapsed:false,extendNew:10,extendRev:50,newToday:[0,0],revToday:[0,0],lrnToday:[0,0],timeToday:[0,0]});
  const model={id:modelId,name:'Studyhub Basic',type:0,mod:seconds,usn:-1,sortf:0,did:deckId,
    flds:['Question','Answer'].map((name,ord)=>({name,ord,sticky:false,rtl:false,font:'Arial',size:20,media:[]})),
    tmpls:[{name:'Card 1',ord:0,qfmt:'{{Question}}',afmt:'{{FrontSide}}<hr id="answer">{{Answer}}',bqfmt:'',bafmt:'',bfont:'',bsize:0,did:null}],
    css:'.card { font-family: Arial; font-size: 20px; text-align: center; color: black; background-color: white; }',latexPre:'',latexPost:'',latexsvg:false,req:[[0,'all',[0]]],tags:[],vers:[]};
  const config={id:1,name:'Default',mod:0,usn:0,maxTaken:60,autoplay:true,replayq:true,timer:0,
    new:{delays:[1,10],ints:[1,4,7],initialFactor:2500,perDay:20,order:1,bury:true,separate:true},
    rev:{perDay:200,ease4:1.3,fuzz:0.05,ivlFct:1,maxIvl:36500,minSpace:1,bury:true},
    lapse:{delays:[10],mult:0,minInt:1,leechFails:8,leechAction:0}};
  try{
    db.run(schema);
    db.run('INSERT INTO col VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',[1,seconds,now,now,11,0,0,0,
      JSON.stringify({activeDecks:[deckId],curDeck:deckId,curModel:String(modelId),nextPos:cards.length+1,sortType:'noteFld',sortBackwards:false,newSpread:0,collapseTime:1200,timeLim:0,dueCounts:true,estTimes:true,addToCur:true}),
      JSON.stringify({[modelId]:model}),JSON.stringify({1:deck(1,'Default'),[deckId]:deck(deckId,name)}),JSON.stringify({1:config}),'{}']);
    for(const [index,card] of cards.entries()){
      const note=await identity('note:'+card.key);const cardId=(await identity('card:'+card.key)).id;
      const source=card.source;
      const citation=source?'<div style="font-size:12px;color:#7d857e;margin-top:10px">Source: '+source.pages.map(page=>{
        const label=html(`${source.pdfName} page ${page}`);
        return source.pdfId&&baseUrl?`<a style="color:inherit" href="${html(new URL('/#/pdf/'+encodeURIComponent(source.pdfId)+'?page='+page,baseUrl).href)}" target="_blank" rel="noopener noreferrer">${label}</a>`:label;
      }).join(' · ')+(source.pdfId?'':' (PDF deleted)')+'</div>':'';
      db.run('INSERT INTO notes VALUES(?,?,?,?,?,?,?,?,?,?,?)',[note.id,note.guid,modelId,seconds,-1,card.demo?' studyhub demo ':' studyhub ',html(card.question)+citation+'\x1f'+html(card.answer),card.question,0,0,'']);
      db.run('INSERT INTO cards VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[cardId,note.id,deckId,0,seconds,-1,0,0,index+1,0,2500,0,0,0,0,0,0,'']);
    }
    return zipSync({'collection.anki2':db.export(),media:strToU8('{}')});
  }finally{db.close();}
}
