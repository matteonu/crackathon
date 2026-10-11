import test from 'node:test';
import assert from 'node:assert/strict';
import { cleanTitle, doneTasks, droppedPlacement, dueLabel, dueState, openTasks, priorityRank, taskDayBounds, topPosition, validTask } from '../src/app/models/task.ts';
import type { Task } from '../src/app/models/task.ts';

const task=(id:string,position:number,extra:Partial<Task>={}):Task=>({id,subjectId:'analysis',title:id,notes:'',due:null,priority:'medium',done:false,completedAt:null,position,createdAt:Number(id.replace(/\D/g,''))||0,...extra});

test('daily cleanup uses local midnight across month, year and daylight-saving boundaries', () => {
  for (const [year, month, day] of [[2026, 2, 29], [2026, 9, 25], [2026, 11, 31], [2028, 1, 29]]) {
    const now = new Date(year, month, day, 23, 59);
    const bounds = taskDayBounds(now);
    assert.equal(bounds.start, new Date(year, month, day).getTime());
    assert.equal(bounds.next, new Date(year, month, day + 1).getTime());
    assert.ok(bounds.start < now.getTime() && bounds.next > now.getTime());
  }
});

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

test('dropping a dragged task places it between its new neighbours',()=>{
  const open=openTasks([task('h1',0,{priority:'high'}),task('h2',1,{priority:'high'}),task('m1',0),task('m2',2),task('l1',0,{priority:'low'})],'analysis');
  // ids in order: h1 h2 m1 m2 l1
  assert.deepEqual(droppedPlacement(open,'m2',2),{priority:'medium',position:-1});   // above m1, still medium
  assert.deepEqual(droppedPlacement(open,'h1',1),{priority:'high',position:2});      // below h2
  assert.deepEqual(droppedPlacement(open,'m1',1),{priority:'high',position:0.5});    // between h1 and h2: becomes high
  assert.deepEqual(droppedPlacement(open,'l1',0),{priority:'high',position:-1});     // to the very top: high
  assert.deepEqual(droppedPlacement(open,'h1',4),{priority:'low',position:1});       // to the bottom, below l1: low
  assert.deepEqual(droppedPlacement(open,'h2',2),{priority:'medium',position:1});    // between m1 and m2
  assert.equal(droppedPlacement(open,'m1',2),null);                                   // dropped where it was
  assert.equal(droppedPlacement(open,'missing',0),null);
});

test('a task dropped between two other priorities keeps its own when it sorts there',()=>{
  const open=openTasks([task('h',0,{priority:'high'}),task('l',0,{priority:'low'}),task('m',5)],'analysis');
  assert.deepEqual(open.map(t=>t.id),['h','m','l']);
  assert.equal(droppedPlacement(open,'m',1),null);
  const hl=openTasks([task('h',0,{priority:'high'}),task('l',0,{priority:'low'}),task('l2',1,{priority:'low'})],'analysis');
  assert.deepEqual(droppedPlacement(hl,'l2',1),{priority:'low',position:-1});        // between h and l: stays low, above l
});

test('a new task lands above everything in its subject',()=>{
  assert.equal(topPosition([],'analysis'),-1);
  assert.equal(topPosition([task('a',3),task('b',-4),task('c',-9,{subjectId:'algebra'})],'analysis'),-5);
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
