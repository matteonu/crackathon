import test from 'node:test';
import assert from 'node:assert/strict';
import { cleanTitle, doneTasks, dueLabel, dueState, movedPosition, openTasks, topPosition, validTask } from '../src/app/models/task.ts';
import type { Task } from '../src/app/models/task.ts';

const task=(id:string,position:number,extra:Partial<Task>={}):Task=>({id,subjectId:'analysis',title:id,notes:'',due:null,done:false,completedAt:null,position,createdAt:Number(id.replace(/\D/g,''))||0,...extra});

test('open tasks follow their manual order, done tasks the latest completion first',()=>{
  const tasks=[task('a1',2),task('b2',1),task('c3',3,{done:true,completedAt:10}),task('d4',0,{done:true,completedAt:20}),task('e5',-1,{subjectId:'algebra'})];
  assert.deepEqual(openTasks(tasks,'analysis').map(t=>t.id),['b2','a1']);
  assert.deepEqual(doneTasks(tasks,'analysis').map(t=>t.id),['d4','c3']);
  assert.deepEqual(openTasks(tasks,'algebra').map(t=>t.id),['e5']);
});

test('a new task lands above everything in its subject',()=>{
  assert.equal(topPosition([],'analysis'),-1);
  assert.equal(topPosition([task('a',3),task('b',-4),task('c',-9,{subjectId:'algebra'})],'analysis'),-5);
});

test('moving a task steps past one neighbour and stops at the ends',()=>{
  const open=[task('a',0),task('b',1),task('c',2)];
  assert.equal(movedPosition(open,'b',-1),-1);          // before a, nothing beyond: a - 1
  assert.equal(movedPosition(open,'a',1),1.5);          // between b and c
  assert.equal(movedPosition(open,'c',1),null);
  assert.equal(movedPosition(open,'a',-1),null);
  assert.equal(movedPosition(open,'missing',1),null);
});

test('titles are collapsed and capped, due dates are described relative to today',()=>{
  assert.equal(cleanTitle('  Solve \n  sheet   4 '),'Solve sheet 4');
  assert.equal(cleanTitle('x'.repeat(600)).length,500);
  assert.equal(dueState('2026-10-09','2026-10-10'),'overdue');
  assert.equal(dueLabel('2026-10-10','2026-10-10'),'Today');
  assert.equal(dueLabel('2026-10-11','2026-10-10'),'Tomorrow');
  assert.equal(dueLabel('2026-12-24','2026-10-10'),'24 Dec');
  assert.equal(dueLabel('2027-01-05','2026-10-10'),'5 Jan 2027');
});

test('only well-formed server rows are accepted',()=>{
  assert.equal(validTask(task('a',0)),true);
  assert.equal(validTask({...task('a',0),due:'2026-13-01'}),false);
  assert.equal(validTask({...task('a',0),title:''}),false);
  assert.equal(validTask({...task('a',0),done:'yes'}),false);
  assert.equal(validTask(null),false);
});
