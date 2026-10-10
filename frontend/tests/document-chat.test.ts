import test from 'node:test';
import assert from 'node:assert/strict';
import { contextPages, visiblePdfPage } from '../src/app/models/pdf-context.ts';
import { canChatWithDocument } from '../src/app/models/material.ts';
import type { Material, DocumentType } from '../src/app/models/material.ts';

test('chat uses the document schema and excludes exercises, notes and folders',()=>{
  const material:Material={id:'doc',subjectId:'math',name:'test.pdf',size:1,added:0,category:'Slides',marker:'To read',kind:'pdf'};
  for(const type of ['slides','exercise_solution','mock_exam','script'] as DocumentType[])assert.equal(canChatWithDocument({...material,type}),true);
  for(const type of ['exercise','summary','cards','mcq',null] as (DocumentType|null)[])assert.equal(canChatWithDocument({...material,type}),false);
  assert.equal(canChatWithDocument({...material,kind:'folder'}),false);
  assert.equal(canChatWithDocument({...material,kind:'txt'}),false);
});

test('page context is clamped at the ends and disabled until the PDF loads',()=>{
  assert.deepEqual(contextPages(0,0),[]);
  assert.deepEqual(contextPages(1,1),[1]);
  assert.deepEqual(contextPages(1,5),[1,2]);
  assert.deepEqual(contextPages(3,5),[2,3,4]);
  assert.deepEqual(contextPages(5,5),[4,5]);
  assert.deepEqual(contextPages(6,5),[]);
});

test('scroll context follows the most visible page, including mixed page sizes',()=>{
  const pages=[{page:1,top:-400,bottom:100},{page:2,top:120,bottom:900},{page:3,top:920,bottom:1100}];
  assert.equal(visiblePdfPage(pages,0,700),2);
  assert.equal(visiblePdfPage(pages,910,1100),3);
  assert.equal(visiblePdfPage(pages,100,120),null);
  assert.equal(visiblePdfPage(pages,0,0),null);
  assert.equal(visiblePdfPage([],0,700),null);
});
