import assert from 'node:assert/strict';
import test from 'node:test';
import { PdfPageCache, pdfRenderScale } from '../src/app/models/pdf-render.ts';

test('PDF resolution follows display width and caps high-density screens',()=>{
  assert.equal(pdfRenderScale(600,800,300,1),0.5);
  assert.equal(pdfRenderScale(600,800,300,2),1);
  assert.equal(pdfRenderScale(600,800,300,4),1);
});

test('large and unusually shaped PDF pages stay within canvas limits',()=>{
  for(const [width,height] of [[10000,10000],[100,100000],[100000,100]]){
    const scale=pdfRenderScale(width,height,20000,2);
    assert.ok(width*height*scale*scale<=4_000_001);
    assert.ok(width*scale<=8192);
    assert.ok(height*scale<=8192);
  }
});

test('page cache releases oldest resources at both page and pixel limits',()=>{
  const disposed:string[]=[];
  const cache=new PdfPageCache<{id:string;pixels:number}>(entry=>disposed.push(entry.id));
  for(let i=0;i<7;i++)cache.put(String(i),{id:String(i),pixels:1_000_000});
  assert.deepEqual(disposed,['0']);
  assert.equal(cache.size,6);
  cache.put('large',{id:'large',pixels:4_000_000});
  assert.deepEqual(disposed,['0','1','2']);
  assert.equal(cache.totalPixels,8_000_000);
  assert.equal(cache.size,5);
});

test('taking a cached page transfers ownership and refreshes recency on return',()=>{
  const disposed:string[]=[];
  const cache=new PdfPageCache<{id:string;pixels:number}>(entry=>disposed.push(entry.id));
  for(let i=0;i<6;i++)cache.put(String(i),{id:String(i),pixels:1});
  const entry=cache.take('0')!;
  assert.equal(cache.totalPixels,5);
  assert.deepEqual(disposed,[]);
  cache.put('0',entry);cache.put('6',{id:'6',pixels:1});
  assert.deepEqual(disposed,['1']);
  assert.equal(cache.take('0'),entry);
});

test('replacing and closing a page cache frees resources and prevents late repopulation',()=>{
  const disposed:string[]=[];
  const cache=new PdfPageCache<{id:string;pixels:number}>(entry=>disposed.push(entry.id));
  cache.put('page',{id:'old',pixels:2});cache.put('page',{id:'new',pixels:3});
  assert.deepEqual(disposed,['old']);
  cache.close();cache.put('late',{id:'late',pixels:1});
  assert.deepEqual(disposed,['old','new','late']);
  assert.equal(cache.size,0);assert.equal(cache.totalPixels,0);
});
