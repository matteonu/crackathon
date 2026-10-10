import test from 'node:test';
import assert from 'node:assert/strict';
import { canGenerateFlashcards, UPLOAD_CATEGORIES, descendants, folderCards, materialName, normalizeMaterial, treeRows, validParent } from '../src/app/models/material.ts';
import type { Material } from '../src/app/models/material.ts';
import { buildApkg } from '../src/app/models/apkg.ts';
import initSqlJs from 'sql.js';
import { unzipSync, strFromU8 } from 'fflate';

const file=(id:string,parentId:string|null,kind:Material['kind']='pdf'):Material=>({id,name:id+(kind==='folder'?'':'.'+kind),parentId,kind,subjectId:'subject',size:0,blob:new Blob(),added:0,category:kind==='pdf'?'Slides':'Notes',marker:'To read'});
const fixture=()=>[file('week1',null,'folder'),file('lecture','week1','folder'),file('notes','lecture','md'),file('slides','week1'),file('root',null)];

test('legacy PDFs remain in Materials with stable card IDs',()=>{
  const old=file('legacy',null);delete old.kind;delete old.parentId;
  old.outputs={flashcards:{cards:[{question:'Q',answer:'A'}]}};
  const migrated=normalizeMaterial(old);
  assert.equal(migrated.kind,'pdf');assert.equal(migrated.parentId,null);
  assert.equal(migrated.outputs?.flashcards?.cards?.[0].id,'legacy-0');
  assert.equal(migrated.outputs?.flashcards?.cards?.[0].demo,true);
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


test('only slides, solutions and scripts offer PDF flashcards, including folder collections',()=>{
  assert.deepEqual(UPLOAD_CATEGORIES,['Slides','Exercises','Solutions','Exams','Scripts']);
  for(const category of ['Slides','Solutions','Scripts','Exercises','Exams','Notes'] as const){
    const pdf={...file(category,null),category,outputs:{flashcards:{cards:[{question:'Q',answer:'A'}]}}};
    const allowed=['Slides','Solutions','Scripts'].includes(category);
    assert.equal(canGenerateFlashcards(pdf),allowed,category);
    assert.equal(folderCards([pdf],null).length,allowed?1:0,category);
  }
});
