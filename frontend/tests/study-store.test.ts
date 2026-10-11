import test from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import '@angular/compiler';
import { createEnvironmentInjector, runInInjectionContext } from '@angular/core';

// Run the real Angular store in Node; transpile its decorators and extensionless imports.
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.') && !/\.[a-z]+$/.test(specifier)) return next(specifier+'.ts', context);
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url.endsWith('.ts') && url.includes('/src/app/')) return {format:'module', shortCircuit:true,
      source:ts.transpileModule(readFileSync(new URL(url),'utf8'), {compilerOptions:{
        target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.ESNext, experimentalDecorators:true,
      }}).outputText};
    return next(url, context);
  },
});
const { StudyStore } = await import('../src/app/services/study-store.ts');
const tick = () => new Promise<void>(resolve => setImmediate(resolve));
const semesters = {selected:'2026W',current:'2026W',available:[{semkez:'2026W',label:'HS26',inCatalogue:true},{semkez:'2027S',label:'FS27',inCatalogue:true}]};
const course = (id:number) => ({id:`course-${id}`,courseId:id,name:`Course ${id}`,shortName:`Course ${id}`,color:'#123456',
  targetHours:10,examDate:'2027-02-14',examStart:null,examEnd:null,completed:false,nextAction:'',hours:{},ects:3,
  lectureId:'test',homepage:null,desiredGrade:null,priority:3,difficulty:3,maxStudyHours:null,lecturePerWeek:2});
const timetable = (ids:number[]) => ({start:'2026-09-14',end:'2026-12-20',events:ids.map(id=>({id:`event-${id}`,subjectId:`course-${id}`,
  date:'2026-10-12',start:'09:00',end:'10:00',label:'Lecture',rooms:[],inheritedFrom:null,biweekly:false}))});
const plan = (ids:number[],semkez='2026W') => ({semkez,label:semkez,start:'2026-12-21',end:'2027-02-14',subjects:ids.map(course),sessions:[],plan:null,timetable:timetable(ids)});

function setup(t:any) {
  const pending:{url:string;method:string;respond:(value:unknown,status?:number)=>void}[]=[];
  t.mock.method(globalThis, 'fetch', (url:string, init:RequestInit={}) => new Promise<Response>(resolve=>{
    pending.push({url,method:init.method??'GET',respond:(value,status=200)=>resolve(new Response(JSON.stringify(value),{status}))});
  }));
  const previous=globalThis.document;
  globalThis.document=new EventTarget() as Document;
  const injector=createEnvironmentInjector([],null!);
  const store=runInInjectionContext(injector,()=>new StudyStore());
  store.announce=()=>{};
  t.after(()=>{injector.destroy();globalThis.document=previous;});
  async function take(url:string, method='GET') {
    for(let attempt=0;attempt<30;attempt++){
      const index=pending.findIndex(request=>request.url===url&&request.method===method);
      if(index>=0)return pending.splice(index,1)[0];
      await tick();
    }
    assert.fail(`Missing ${method} ${url}; pending: ${JSON.stringify(pending)}`);
  }
  const metadata=async()=>{(await take('/api/semesters')).respond(semesters);};
  return {store,take,metadata,pending};
}

test('late plan responses cannot erase a newer course or timetable', async t=>{
  const {store,take,metadata}=setup(t);
  await metadata();
  const old=await take('/api/semesters/2026W/plan');
  const latest=store.load();
  await metadata();
  (await take('/api/semesters/2026W/plan')).respond(plan([1,2]));
  await latest;
  (await take('/api/semesters/2026W/timetable/refresh','POST')).respond(timetable([1,2]));
  old.respond(plan([1]));
  await tick();
  assert.deepEqual(store.subjects().map(s=>s.id),['course-1','course-2']);
  assert.deepEqual(store.calendarCourses().map(e=>e.subjectId),['course-1','course-2']);
});

test('consecutive adds reload the whole course list and reject an older timetable refresh', async t=>{
  const {store,take,metadata,pending}=setup(t);
  await metadata();(await take('/api/semesters/2026W/plan')).respond(plan([]));
  const initialTimes=await take('/api/semesters/2026W/timetable/refresh','POST');
  const first=store.addCourse({id:1,title:'One'} as any);
  const second=store.addCourse({id:2,title:'Two'} as any);
  const add=await take('/api/semesters/2026W/courses','POST');
  assert.equal(pending.filter(r=>r.url.endsWith('/courses')).length,0);
  add.respond({});await metadata();
  (await take('/api/semesters/2026W/plan')).respond(plan([1]));await first;
  const firstTimes=await take('/api/semesters/2026W/timetable/refresh','POST');
  (await take('/api/semesters/2026W/courses','POST')).respond({});await metadata();
  (await take('/api/semesters/2026W/plan')).respond(plan([1,2]));await second;
  (await take('/api/semesters/2026W/timetable/refresh','POST')).respond(timetable([1,2]));
  firstTimes.respond(timetable([1]));initialTimes.respond(timetable([]));await tick();
  assert.deepEqual(store.subjects().map(s=>s.id),['course-1','course-2']);
  assert.deepEqual(store.calendarCourses().map(e=>e.subjectId),['course-1','course-2']);
  assert.equal(store.refreshingTimetable(),false);
});

test('refresh updates calendar without changing the chosen week and preserves saved times on failure', async t=>{
  const {store,take,metadata}=setup(t);
  await metadata();(await take('/api/semesters/2026W/plan')).respond(plan([1]));
  const times=await take('/api/semesters/2026W/timetable/refresh','POST');
  store.setWeek('2026-10-19');
  times.respond(timetable([1,2]));await tick();
  assert.equal(store.weekStart(),'2026-10-19');
  assert.equal(store.calendarCourses().length,2);
  const reloaded=store.load();await metadata();
  (await take('/api/semesters/2026W/plan')).respond(plan([1,2]));await reloaded;
  (await take('/api/semesters/2026W/timetable/refresh','POST')).respond({error:'offline'},503);await tick();
  assert.equal(store.calendarCourses().length,2);
  assert.equal(store.weekStart(),'2026-10-19');
  assert.match(store.timetableError(),/saved timetable/);
});

test('switching semester ignores the old semester refresh', async t=>{
  const {store,take,metadata}=setup(t);
  await metadata();(await take('/api/semesters/2026W/plan')).respond(plan([1]));
  const old=await take('/api/semesters/2026W/timetable/refresh','POST');
  const switching=store.selectSemester('2027S');
  (await take('/api/semesters/selected','PUT')).respond({});await metadata();
  (await take('/api/semesters/2027S/plan')).respond(plan([3],'2027S'));await switching;
  (await take('/api/semesters/2027S/timetable/refresh','POST')).respond(timetable([3]));
  old.respond(timetable([1]));await tick();
  assert.equal(store.semkez(),'2027S');
  assert.deepEqual(store.calendarCourses().map(e=>e.subjectId),['course-3']);
});
