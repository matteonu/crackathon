import test from 'node:test';
import assert from 'node:assert/strict';
import { cleanTitle, doneTasks, dueLabel, dueState, movedPosition, openTasks, priorityRank, topPosition, validTask } from '../src/app/models/task.ts';
import type { Task } from '../src/app/models/task.ts';

const task=(id:string,position:number,extra:Partial<Task>={}):Task=>({id,subjectId:'analysis',title:id,notes:'',due:null,priority:'medium',done:false,completedAt:null,position,createdAt:Number(id.replace(/\D/g,''))||0,...extra});

test('open tasks follow their manual order, done tasks the latest completion first',()=>{
  const tasks=[task('a1',2),task('b2',1),task('c3',3,{done:true,completedAt:10}),task('d4',0,{done:true,completedAt:20}),task('e5',-1,{subjectId:'algebra'})];
  assert.deepEqual(openTasks(tasks,'analysis').map(t=>t.id),['b2','a1']);
  assert.deepEqual(doneTasks(tasks,'analysis').map(t=>t.id),['d4','c3']);
  assert.deepEqual(openTasks(tasks,'algebra').map(t=>t.id),['e5']);
});

test('open tasks sort by priority first, then by their manual order',()=>{
  const tasks=[task('a1',0,{priority:'low'}),task('b2',2),task('c3',5,{priority:'high'}),task('d4',1),task('e5',-3,{priority:'high',done:true,completedAt:1})];
  assert.deepEqual(openTasks(tasks,'analysis').map(t=>t.id),['c3','d4','b2','a1']);
  assert.deepEqual([priorityRank('high'),priorityRank('medium'),priorityRank('low')],[0,1,2]);
});

test('moving a task stays within its priority',()=>{
  const open=openTasks([task('h',9,{priority:'high'}),task('m1',0),task('m2',1),task('l',-5,{priority:'low'})],'analysis');
  assert.equal(movedPosition(open,'m1',-1),null);       // the high task above is another group
  assert.equal(movedPosition(open,'m2',1),null);        // so is the low one below
  assert.equal(movedPosition(open,'m2',-1),-1);         // before m1, nothing beyond in the group
  assert.equal(movedPosition(open,'h',1),null);
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
  assert.equal(validTask({...task('a',0),priority:'urgent' as never}),false);
  assert.equal(validTask({...task('a',0),priority:undefined as never}),false);
  assert.equal(validTask(null),false);
});
