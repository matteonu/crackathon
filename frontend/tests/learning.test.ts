import test from 'node:test';
import assert from 'node:assert/strict';
import { learningPatch, parseStudyResult } from '../src/app/models/learning.ts';
import type { StudyResult } from '../src/app/models/learning.ts';
import type { Material } from '../src/app/models/material.ts';

const file:Material={id:'pdf-id',subjectId:'subject',name:'lecture.pdf',size:0,blob:new Blob(),added:0,kind:'pdf',category:'Slides',marker:'To read',
  outputs:{flashcards:{cards:[{id:'demo',question:'Example',answer:'Example',demo:true},{id:'manual',question:'My question',answer:'My answer',demo:false}]}}};
const result:StudyResult={id:'pdf-id',status:'complete',documents:[{abstract:'The lecture explains active recall.',sentence_count:1,requested_sentences:1,complete:true,questions:[{question:'What is active recall?',answer:'Retrieving information from memory.'}]}]};

test('saved Python JSON supplies a read-only description and real cards, replacing demo cards',()=>{
  const patch=learningPatch(file,parseStudyResult(result,file.id));
  assert.equal(patch.description,result.documents[0].abstract);
  assert.equal(patch.outputs.summary.text,patch.description);
  assert.deepEqual(patch.outputs.flashcards.cards.map(card=>card.id),['pipeline:pdf-id:0','manual']);
  assert.equal(patch.outputs.flashcards.cards[0].demo,false);
  assert.equal(patch.outputs.flashcards.cards[0].generated,true);
});

test('polling and retries preserve manual cards without duplicating generated cards',()=>{
  const first={...file,...learningPatch(file,result)};
  const second=learningPatch(first,result);
  assert.deepEqual(second.outputs.flashcards.cards,first.outputs.flashcards.cards);
});

test('a partial summary appears while questions are still being generated',()=>{
  const partial:StudyResult={id:file.id,status:'running',documents:[{abstract:'One sentence.',sentence_count:1}]};
  const patch=learningPatch(file,parseStudyResult(partial,file.id));
  assert.equal(patch.description,'One sentence.');
  assert.equal(patch.processing.status,'running');
  assert.deepEqual(patch.outputs.flashcards.cards.map(card=>card.id),['manual']);
});

test('wrong document IDs, malformed cards and incomplete final results are rejected',()=>{
  assert.throws(()=>parseStudyResult({...result,id:'another-file'},file.id));
  assert.throws(()=>parseStudyResult({...result,documents:[{...result.documents[0],questions:[{question:'Q'}]}]},file.id));
  assert.throws(()=>parseStudyResult({...result,documents:[]},file.id));
  assert.throws(()=>parseStudyResult({...result,documents:[{...result.documents[0],sentence_count:2}]},file.id));
  assert.equal(parseStudyResult({id:file.id,status:'error',error:'Key is missing.',documents:[]},file.id).error,'Key is missing.');
});

test('mode switches discard previous generated content, preserve manual cards and reject another mode',()=>{
  const shallow={...file,...learningPatch(file,result)};
  const pending:StudyResult={id:file.id,mode:'deep',status:'queued',documents:[]};
  const patch=learningPatch(shallow,parseStudyResult(pending,file.id,'deep'));
  assert.equal(patch.processing.mode,'deep');
  assert.equal(patch.description,'');
  assert.deepEqual(patch.outputs.flashcards.cards.map(card=>card.id),['manual']);
  assert.throws(()=>parseStudyResult({...result,mode:'shallow'},file.id,'deep'),/different processing mode/);
  const deep={...result,mode:'deep' as const};
  assert.equal(learningPatch({...shallow,...patch},parseStudyResult(deep,file.id,'deep')).processing.mode,'deep');
});
