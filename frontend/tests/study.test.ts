import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { addDays, dailyTotal, isValidDate, mondayOf, sumHours, validateData, weekDays, segmentedDate, validSession, sessionsOverlap } from '../src/app/models/study.ts';
import type { StudyData } from '../src/app/models/study.ts';

const seed=JSON.parse(readFileSync(new URL('./fixtures/study-data.json',import.meta.url),'utf8')) as StudyData;

test('sample preserves the five spreadsheet totals and 320-hour target',()=>{
  assert.equal(validateData(seed),true);
  assert.deepEqual(seed.subjects.map(s=>sumHours(s)),[69,135,64,62,23]);
  assert.equal(seed.subjects.reduce((sum,s)=>sum+sumHours(s),0),353);
  assert.equal(seed.subjects.reduce((sum,s)=>sum+s.targetHours,0),320);
  assert.equal(seed.subjects.find(s=>s.id==='probability')!.hours['2025-01-06'],2);
});

test('weekly and daily aggregates match the selected seven dates',()=>{
  const week=weekDays('2025-01-06');
  assert.deepEqual(week,['2025-01-06','2025-01-07','2025-01-08','2025-01-09','2025-01-10','2025-01-11','2025-01-12']);
  assert.deepEqual(week.map(d=>dailyTotal(seed.subjects,d)),[9,9,9,8,2,11,9]);
  assert.equal(seed.subjects.reduce((sum,s)=>sum+sumHours(s,week),0),57);
});

test('editing a recorded value changes totals once without changing the seed',()=>{
  const data=structuredClone(seed);const subject=data.subjects[2];
  subject.hours['2025-01-06']=3.5;
  assert.equal(sumHours(subject),65.5);
  assert.equal(dailyTotal(data.subjects,'2025-01-06'),10.5);
  assert.equal(subject.targetHours-sumHours(subject),-.5);
  assert.equal(validateData(data),true);
  assert.equal(seed.subjects[2].hours['2025-01-06'],2);
});

test('zero and an unrecorded cell remain distinct through JSON round-trip',()=>{
  const data=structuredClone(seed);data.subjects[0].hours['2025-01-06']=0;
  const copy=JSON.parse(JSON.stringify(data)) as StudyData;
  assert.equal(copy.subjects[0].hours['2025-01-06'],0);
  assert.equal(copy.subjects[0].hours['2025-01-07'],null);
  assert.equal(validateData(copy),true);
});

test('Monday-based weeks handle year boundaries, leap days, and DST',()=>{
  assert.equal(mondayOf('2025-01-01'),'2024-12-30');
  assert.equal(mondayOf('2025-01-05'),'2024-12-30');
  assert.equal(addDays('2024-02-28',1),'2024-02-29');
  assert.equal(addDays('2025-03-30',1),'2025-03-31');
  assert.equal(addDays('2025-10-26',-1),'2025-10-25');
  assert.equal(isValidDate('2025-02-29'),false);
  assert.equal(isValidDate('2024-02-29'),true);
});

test('import rejects impossible totals, bad dates, and duplicate identifiers',()=>{
  const data=structuredClone(seed);
  data.subjects[0].hours['2025-01-06']=24;
  assert.equal(validateData(data),false);
  data.subjects[0].hours['2025-01-06']=-1;
  assert.equal(validateData(data),false);
  data.subjects[0].hours['2025-01-06']=null;
  data.subjects[0].examDate='2025-02-30';
  assert.equal(validateData(data),false);
  data.subjects[0].examDate='2025-02-28';
  data.subjects[0].id=data.subjects[1].id;
  assert.equal(validateData(data),false);
  assert.equal(validateData({version:1,dates:[]}),false);
});

test('reference date must lie in the imported phase and cards must balance',()=>{
  const data=structuredClone(seed);data.referenceDate='2028-01-01';
  assert.equal(validateData(data),false);
  data.referenceDate=seed.referenceDate;data.anki[0].total++;
  assert.equal(validateData(data),false);
});

test('segmented dates reject partial, impossible, and non-numeric input',()=>{
  assert.equal(segmentedDate('6','1','2025'),'2025-01-06');
  assert.equal(segmentedDate('29','02','2024'),'2024-02-29');
  for(const [day,month,year] of [['29','02','2025'],['31','04','2025'],['','01','2025'],['1','1','25'],['1e','01','2025'],['00','01','2025']]){
    assert.equal(segmentedDate(day,month,year),null);
  }
});

test('planned sessions honor both exam-session boundaries and midnight',()=>{
  const data=structuredClone(seed);
  data.examSession={start:'2025-01-06',end:'2025-01-12'};
  const session={id:'plan-1',subjectId:data.subjects[0].id,date:'2025-01-06',start:'22:00',hours:2};
  assert.equal(validSession(session,data),true);
  assert.equal(validSession({...session,date:'2025-01-12'},data),true);
  assert.equal(validSession({...session,date:'2025-01-05'},data),false);
  assert.equal(validSession({...session,date:'2025-01-13'},data),false);
  assert.equal(validSession({...session,hours:2.25},data),false);
  assert.equal(validSession({...session,hours:0},data),false);
  assert.equal(validSession({...session,start:'24:00'},data),false);
  assert.equal(validSession({...session,subjectId:'missing'},data),false);
});

test('adjacent sessions are valid but overlaps and duplicate IDs are rejected',()=>{
  const data=structuredClone(seed);
  const first={id:'a',subjectId:data.subjects[0].id,date:'2025-01-06',start:'09:00',hours:2};
  const next={...first,id:'b',start:'11:00'};
  assert.equal(sessionsOverlap(first,next),false);
  data.sessions=[first,next];
  assert.equal(validateData(data),true);
  data.sessions=[first,{...next,start:'10:45'}];
  assert.equal(validateData(data),false);
  data.sessions=[first,{...next,id:'a'}];
  assert.equal(validateData(data),false);
});

test('planning never contributes to recorded totals and survives JSON export',()=>{
  const data=structuredClone(seed);
  data.sessions=[{id:'a',subjectId:data.subjects[0].id,date:'2025-01-06',start:'09:00',hours:2}];
  const copy=JSON.parse(JSON.stringify(data)) as StudyData;
  assert.equal(validateData(copy),true);
  assert.equal(copy.sessions?.[0].hours,2);
  assert.equal(copy.subjects.reduce((sum,s)=>sum+sumHours(s),0),353);
});

test('legacy data still imports, and metadata and Anki associations are validated',()=>{
  const data=structuredClone(seed);delete data.examSession;
  assert.equal(validateData(data),true);
  Object.assign(data.subjects[0],{ects:8,lectureId:'401-1234-00',homepage:'https://example.org/course'});
  data.anki[0].subjectId=data.subjects[0].id;
  assert.equal(validateData(data),true);
  data.subjects[0].homepage='javascript:alert(1)';
  assert.equal(validateData(data),false);
  data.subjects[0].homepage='';data.anki[0].subjectId='unknown';
  assert.equal(validateData(data),false);
});
