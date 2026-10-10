import test from 'node:test';
import assert from 'node:assert/strict';
import { recallKey, recallSnapshot, recallTreeRows } from '../src/app/models/recall.ts';
import type { RecallAnalytics } from '../src/app/models/recall.ts';

const row=(path:string[],cards=10):RecallAnalytics=>({path,name:path.at(-1)??'All flashcards',label:path.join(' / '),priority:1,cards,reviews:0,mistakes:0,lapses:0,success_rate:null,due_cards:cards,overdue_review_cards:0,mature_cards:0,average_interval_days:0,average_response_seconds:null,states:{new:cards,learning:0,relearning:0,review:0},ratings:{again:0,hard:0,good:0,easy:0}});

test('snapshot counts learning and relearning cards as learned and partitions the total',()=>{
  const stats=row([]);stats.mature_cards=2;stats.states={new:3,learning:2,relearning:1,review:4};
  assert.deepEqual(recallSnapshot(stats),{mature:2,learned:5,left:3,total:10,progress:70});
  assert.deepEqual(recallSnapshot(row([],0)),{mature:0,learned:0,left:0,total:0,progress:0});
});

test('expanding a hierarchy reveals only children whose ancestors are open',()=>{
  const data=[row(['subject','week','deck']),row(['subject','week']),row(['subject']),row([]),row(['subject','other'])];
  const expanded=new Set([recallKey([])]);
  assert.deepEqual(recallTreeRows(data,expanded).map(item=>item.row.path),[[],['subject']]);
  expanded.add(recallKey(['subject']));expanded.add(recallKey(['subject','week']));
  assert.deepEqual(recallTreeRows(data,expanded).map(item=>item.row.path),[[],['subject'],['subject','week'],['subject','week','deck'],['subject','other']]);
  expanded.delete(recallKey(['subject']));
  assert.equal(recallTreeRows(data,expanded).length,2);
});

test('hierarchy keys distinguish path segments containing separators',()=>{
  assert.notEqual(recallKey(['a/b']),recallKey(['a','b']));
});
