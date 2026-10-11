import test from 'node:test';
import assert from 'node:assert/strict';
import { canGenerateFlashcards, CATEGORY_DOCUMENT_TYPES, UPLOAD_CATEGORIES, descendants, folderCards, materialCards, materialName, materialPath, normalizeMaterial, sourcePageUrl, treeRows, validParent } from '../src/app/models/material.ts';
import type { Material } from '../src/app/models/material.ts';
import { buildApkg } from '../src/app/models/apkg.ts';
import initSqlJs from 'sql.js';
import { unzipSync, strFromU8 } from 'fflate';

const file=(id:string,parentId:string|null,kind:Material['kind']='pdf'):Material=>({id,name:id+(kind==='folder'?'':'.'+kind),parentId,kind,subjectId:'subject',size:0,blob:new Blob(),added:0,category:kind==='pdf'?'Slides':'Notes',marker:'To read'});
const fixture=()=>[file('week1',null,'folder'),file('lecture','week1','folder'),file('notes','lecture','md'),file('slides','week1'),file('root',null)];

test('file paths include nested folders and follow moves and renames',()=>{
  const files=fixture(),notes=files.find(f=>f.id==='notes')!;
  assert.equal(materialPath(files,notes),'Materials / week1 / lecture');
  assert.equal(materialPath(files,{...notes,parentId:null}),'Materials');
  assert.equal(materialPath(files,{...notes,parentId:'week1'}),'Materials / week1');
  assert.equal(materialPath(files.map(f=>f.id==='week1'?{...f,name:'Week 1'}:f),notes),'Materials / Week 1 / lecture');
});

test('file paths tolerate missing parents and cycles without crossing subjects',()=>{
  const notes=file('notes','missing','md');
  assert.equal(materialPath([],notes),'Materials');
  const folder=file('missing','notes','folder');
  assert.equal(materialPath([notes,folder],notes),'Materials / missing');
  assert.equal(materialPath([{...folder,subjectId:'other'}],notes),'Materials');
});

test('legacy PDFs remain in Materials with stable card IDs',()=>{
  const old=file('legacy',null);delete old.kind;delete old.parentId;
  old.outputs={flashcards:{cards:[{question:'Q',answer:'A'}]}};
  const migrated=normalizeMaterial(old);
  assert.equal(migrated.kind,'pdf');assert.equal(migrated.parentId,null);
  assert.equal(migrated.type,'slides');
  assert.equal(migrated.outputs?.flashcards?.cards?.[0].id,'legacy-0');
  assert.equal(migrated.outputs?.flashcards?.cards?.[0].demo,true);
});

test('upload types match the backend codes and stored types control card eligibility',()=>{
  assert.deepEqual(UPLOAD_CATEGORIES.map(category=>CATEGORY_DOCUMENT_TYPES[category]),
    ['slides','exercise','exercise_solution','mock_exam','script']);
  assert.equal(normalizeMaterial({...file('old',null),category:'Books'}).type,null);
  assert.equal(normalizeMaterial(file('folder',null,'folder')).type,null);
  const pdf={...file('typed',null),type:'mock_exam' as const};
  assert.equal(normalizeMaterial(pdf).type,'mock_exam');
  assert.equal(canGenerateFlashcards(pdf),false);
  assert.equal(canGenerateFlashcards({...pdf,type:'script',category:'Notes'}),true);
  assert.equal(canGenerateFlashcards({...pdf,type:null}),false);
});

test('collapsed trees and filtered descendants retain their ancestors',()=>{
  const files=fixture();
  assert.deepEqual(treeRows(files,new Set()).map(row=>row.material.id),['week1','root']);
  const expanded=treeRows(files,new Set(['week1','lecture']));
  assert.equal(expanded.find(row=>row.material.id==='notes')?.depth,2);
  assert.deepEqual(treeRows(files,new Set(),'notes').map(row=>row.material.id),['week1','lecture','notes']);
});

test('folder card sets include descendants exactly once and exclude siblings',()=>{
  const files=fixture();for(const f of files.filter(f=>f.kind!=='folder'))f.outputs={flashcards:{cards:[{id:f.id,question:'Q',answer:'A'}]}};
  assert.deepEqual(folderCards(files,'week1').map(c=>c.fileId),['notes','slides']);
  assert.equal(folderCards(files,null).length,3);assert.equal(folderCards(files,'lecture').length,1);
  assert.equal(descendants(files,'week1').length,3);
});

test('moves cannot create cycles or cross subject boundaries',()=>{
  const files=fixture();
  assert.equal(validParent(files,'subject','lecture','week1'),false);
  assert.equal(validParent(files,'subject','week1','week1'),false);
  assert.equal(validParent(files,'another-subject','week1','root'),false);
  assert.equal(validParent(files,'subject','slides','root'),false);
  assert.equal(validParent(files,'subject','week1','root'),true);
  assert.equal(validParent(files,'subject',null,'root'),true);
  assert.equal(materialName(' Notes ','md'),'Notes.md');
  assert.equal(materialName('Notes.MD','md'),'Notes.MD');
  assert.throws(()=>materialName('../notes','txt'));
});

test('independent decks expose cards once, preserve IDs on moves and retain source links',()=>{
  const folder=file('folder',null,'folder');
  const source=file('pdf',null,'pdf');
  const deck=file('deck',null,'deck');
  deck.sourcePdfId=source.id;
  deck.outputs={flashcards:{cards:[{id:'stable-card',question:'Q',answer:'A',generated:true,demo:false}]}};
  const files=[folder,source,deck];
  assert.equal(folderCards(files,null).length,1);
  assert.equal(folderCards(files,null)[0].fileId,source.id);
  deck.parentId=folder.id;
  assert.equal(folderCards(files,folder.id)[0].key,'stable-card');
  deck.sourcePdfId=null;
  assert.equal(folderCards(files,folder.id)[0].fileId,deck.id);
  assert.equal(materialName('Renamed deck','deck'),'Renamed deck');
});

test('APKG is a readable Anki SQLite package with escaped content and stable note identity',async()=>{
  const SQL=await initSqlJs();
  const cards=[{key:'a',fileId:'f',fileName:'Notes.md',question:'What is <script>?',answer:'A & B\nC',demo:true},{key:'b',fileId:'g',fileName:'Slides.pdf',question:'Second question',answer:'Second answer',demo:false}];
  const bytes=await buildApkg(SQL,cards,'Week 1','subject:week1');
  const entries=unzipSync(bytes);assert.deepEqual(Object.keys(entries).sort(),['collection.anki2','media']);
  assert.equal(strFromU8(entries['media']),'{}');
  const db=new SQL.Database(entries['collection.anki2']);
  assert.equal(db.exec('PRAGMA integrity_check')[0].values[0][0],'ok');
  assert.equal(db.exec('SELECT COUNT(*) FROM notes')[0].values[0][0],2);
  assert.equal(db.exec('SELECT COUNT(*) FROM cards')[0].values[0][0],2);
  const fields=db.exec("SELECT flds,tags FROM notes WHERE tags LIKE '%demo%'")[0].values[0];
  assert.equal(fields[0],'What is &lt;script&gt;?\x1fA &amp; B<br>C');
  const decks=JSON.parse(db.exec('SELECT decks FROM col')[0].values[0][0] as string);
  assert.ok(Object.values(decks).some((d:any)=>d.name==='Week 1'));
  const ids=db.exec('SELECT guid FROM notes ORDER BY guid')[0].values;
  const second=unzipSync(await buildApkg(SQL,cards,'Renamed folder','subject:week1'));
  const reopened=new SQL.Database(second['collection.anki2']);
  assert.deepEqual(reopened.exec('SELECT guid FROM notes ORDER BY guid')[0].values,ids);
  await assert.rejects(buildApkg(SQL,[],'Empty','empty'));
  db.close();reopened.close();
});


test('folder APKG includes every nested deck, while a deck APKG contains only its own cards',async()=>{
  const deck=(id:string,parentId:string|null,count:number):Material=>({...file(id,parentId,'deck'),
    marker:'Done',outputs:{flashcards:{cards:Array.from({length:count},(_,i)=>({id:`${id}-${i}`,question:`${id} question ${i}`,answer:'Answer'}))}}});
  const direct=deck('direct','folder',8),nested=deck('nested','child',7),deep=deck('deep','grandchild',6);
  const files=[file('folder',null,'folder'),file('child','folder','folder'),file('grandchild','child','folder'),
    direct,nested,deep,deck('outside',null,3)];
  // Filtering and collapsed folders change the explorer, not what the folder download contains.
  assert.deepEqual(treeRows(files,new Set(),'direct').map(row=>row.material.id),['folder','direct']);
  const SQL=await initSqlJs();
  for(const [cards,name,key,expected] of [
    [folderCards(files,'folder'),'Folder','subject:folder',21],
    [materialCards(nested),'Nested deck','subject:nested',7],
  ] as const){
    const entries=unzipSync(await buildApkg(SQL,cards,name,key));
    const db=new SQL.Database(entries['collection.anki2']);
    try{
      assert.equal(db.exec('PRAGMA integrity_check')[0].values[0][0],'ok');
      assert.equal(db.exec('SELECT count(*) FROM cards')[0].values[0][0],expected);
      assert.equal(db.exec('SELECT count(DISTINCT guid) FROM notes')[0].values[0][0],expected);
      assert.equal(db.exec("SELECT count(*) FROM notes WHERE flds LIKE 'outside %'")[0].values[0][0],0);
      if(key==='subject:nested')assert.equal(db.exec("SELECT count(*) FROM notes WHERE flds NOT LIKE 'nested %'")[0].values[0][0],0);
    }finally{db.close();}
  }
});

test('source links survive collections and APKG exports without changing note IDs or field counts',async()=>{
  const source={pdfId:'pdf-id',pdfName:'Lecture <1>.pdf',pages:[2,4],evidence:'The reference passage.'};
  const deck={...file('deck','folder','deck'),outputs:{flashcards:{cards:[{id:'card-id',question:'Question?',answer:'Answer.',source}]}}};
  const cards=folderCards([file('folder',null,'folder'),deck],'folder');
  assert.deepEqual(cards[0].source,source);
  const SQL=await initSqlJs();
  const unpack=async(items:typeof cards)=>new SQL.Database(unzipSync(await buildApkg(SQL,items,'Folder','deck-id','https://study.example/'))['collection.anki2']);
  const original=await unpack(cards.map(card=>({...card,source:undefined}))),referenced=await unpack(cards);
  const deleted=await unpack(cards.map(card=>({...card,source:{...source,pdfId:null}})));
  try{
    assert.deepEqual(referenced.exec('SELECT guid FROM notes')[0].values,original.exec('SELECT guid FROM notes')[0].values);
    const fields=(referenced.exec('SELECT flds FROM notes')[0].values[0][0] as string).split('\x1f');
    assert.equal(fields.length,2);assert.equal(fields[1],'Answer.');
    for(const page of source.pages){
      assert.ok(fields[0].includes('https://study.example'+sourcePageUrl(source.pdfId,page)));
      assert.ok(fields[0].includes(`Lecture &lt;1&gt;.pdf page ${page}`));
    }
    const removed=deleted.exec('SELECT flds FROM notes')[0].values[0][0] as string;
    assert.ok(removed.includes('(PDF deleted)'));assert.ok(!removed.includes('href='));
    assert.equal(referenced.exec('PRAGMA integrity_check')[0].values[0][0],'ok');
  }finally{original.close();referenced.close();deleted.close();}
});

test('only slides, solutions and scripts offer PDF flashcards, including folder collections',()=>{
  assert.deepEqual(UPLOAD_CATEGORIES,['Slides','Exercises','Solutions','Exams','Scripts']);
  for(const category of ['Slides','Solutions','Scripts','Exercises','Exams','Notes'] as const){
    const pdf={...file(category,null),category,outputs:{flashcards:{cards:[{question:'Q',answer:'A'}]}}};
    const allowed=['Slides','Solutions','Scripts'].includes(category);
    assert.equal(canGenerateFlashcards(pdf),allowed,category);
    assert.equal(folderCards([pdf],null).length,allowed?1:0,category);
  }
});
