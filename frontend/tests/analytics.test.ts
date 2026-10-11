import test from 'node:test';
import assert from 'node:assert/strict';
import { activityWeeks, asOfDate, balanceDelta, consistency, dailySeries, pace, planAdherence, planDeviation, plannedAhead, recentPlanVsRecorded, subjectStats, weekdayProfile, weeklySeries } from '../src/app/models/analytics.ts';
import type { StudyData, Subject } from '../src/app/models/study.ts';
import type { DayPoint } from '../src/app/models/analytics.ts';

// A 14-day phase: Mon 2027-01-04 .. Sun 2027-01-17.
const dates=Array.from({length:14},(_,i)=>`2027-01-${String(4+i).padStart(2,'0')}`);
const subject=(id:string,targetHours:number,examDate:string,hours:Record<string,number|null>):Subject=>({id,name:id,shortName:id,color:'#2598A2',targetHours,examDate,completed:false,nextAction:'',hours});
const data=():StudyData=>({version:1,semester:'HS26',referenceDate:'2027-01-10',dates,notes:'',anki:[],
  subjects:[subject('a',20,'2027-01-15',{'2027-01-04':2,'2027-01-05':3,'2027-01-07':1}),subject('b',10,'2027-01-20',{'2027-01-05':1,'2027-01-08':4})],
  examSession:{start:dates[0],end:dates[13]},
  sessions:[{id:'s1',subjectId:'a',date:'2027-01-05',start:'09:00',hours:2},{id:'s2',subjectId:'b',date:'2027-01-06',start:'09:00',hours:3},{id:'s3',subjectId:'a',date:'2027-01-12',start:'09:00',hours:2.5}]});

test('activity columns align Monday-first across months and preserve blank versus recorded zero',()=>{
  const phase=data();
  phase.dates=['2027-01-31','2027-02-01','2027-02-02'];
  phase.subjects=[subject('a',20,'2027-02-15',{'2027-01-31':0,'2027-02-01':3}),subject('b',10,'2027-02-15',{'2027-02-01':3})];
  const weeks=activityWeeks(phase);
  assert.deepEqual(weeks.map(w=>[w.start,w.month]),[['2027-01-25','Jan'],['2027-02-01','Feb']]);
  assert.ok(weeks[0].days.slice(0,6).every(day=>day===null));
  assert.deepEqual(weeks[0].days[6],{date:'2027-01-31',hours:0,level:0,recorded:true});
  assert.deepEqual(weeks[1].days[0],{date:'2027-02-01',hours:6,level:4,recorded:true});
  assert.deepEqual(weeks[1].days[1],{date:'2027-02-02',hours:0,level:0,recorded:false});
  assert.ok(weeks[1].days.slice(2).every(day=>day===null));
  assert.deepEqual(activityWeeks({...phase,dates:[]}),[]);
});

test('activity colors use stable hour thresholds, including fractional hours',()=>{
  const phase=data();
  phase.subjects=[subject('a',20,'2027-01-15',Object.fromEntries(dates.slice(0,7).map((date,i)=>[date,[0,.5,1.9,2,3.9,4,6][i]])))];
  assert.deepEqual(activityWeeks(phase)[0].days.map(day=>day!.level),[0,1,1,2,2,3,4]);
});

test('as-of is today clamped to the phase, or the last recorded day when that is later',()=>{
  assert.equal(asOfDate(data(),'2026-12-01'),'2027-01-08');   // before the phase, but hours exist up to the 8th
  assert.equal(asOfDate(data(),'2027-01-10'),'2027-01-10');
  assert.equal(asOfDate(data(),'2027-03-01'),'2027-01-17');
});

test('daily and weekly series add recorded and planned hours per day and per week',()=>{
  const days=dailySeries(data());
  assert.equal(days.length,14);
  assert.deepEqual([days[1].recorded,days[1].planned,days[1].bySubject,days[1].weekday],[4,2,{a:3,b:1},1]);
  const weeks=weeklySeries(data(),days);
  assert.deepEqual(weeks.map(w=>[w.start,w.recorded,w.planned,w.target]),[['2027-01-04',11,5,15],['2027-01-11',0,2.5,15]]);
});

test('pace compares recorded hours with an even share of the target',()=>{
  const p=pace(data(),'2027-01-10');
  assert.deepEqual([p.elapsedDays,p.totalDays,p.remainingDays,p.recorded,p.target],[7,14,7,11,30]);
  assert.equal(p.expected,15);
  assert.equal(p.projected,22);          // 11 h in 7 days -> 22 over 14
  assert.equal(p.neededPerDay,2.7);      // 19 h left over 7 days
});

test('subject stats give remaining hours, needed pace and a status, exam-sorted',()=>{
  const [a,b]=subjectStats(data(),'2027-01-10');
  assert.equal(a.subject.id,'a');
  assert.deepEqual([a.recorded,a.remaining,a.percent,a.daysToExam,a.neededPerDay,a.status,a.plannedAhead],[6,14,30,5,2.8,'on-track',2.5]);
  assert.deepEqual([b.recorded,b.remaining,b.daysToExam,b.neededPerDay,b.status],[5,5,10,0.5,'on-track']);
  assert.equal(subjectStats(data(),'2027-01-16')[0].status,'at-risk');   // exam of a passed with hours left
  const worst=balanceDelta([a,b])!;
  assert.equal(worst.subject.id,'a');    // a has 55% of the time but 67% of the targets (b mirrors it; ties keep the first)
  assert.equal(worst.delta,-12.1);
});

test('consistency counts streaks, gaps and a typical day',()=>{
  const c=consistency(dailySeries(data()),'2027-01-10');
  assert.deepEqual([c.recordedDays,c.restDays,c.elapsedDays,c.currentStreak,c.longestStreak,c.longestBreak],[4,0,7,0,2,2]);
  assert.equal(c.averagePerRecordedDay,2.8);
  assert.equal(c.medianPerRecordedDay,3);    // recorded days: 2, 4, 1, 4
  assert.equal(c.bestDay?.date,'2027-01-05');
});

test('a day recorded as 0 is a rest day: it keeps the streak and is not a break',()=>{
  const d=data();
  d.subjects[0].hours['2027-01-06']=0;    // Wed: deliberately off
  d.subjects[1].hours['2027-01-09']=0;    // Sat: off, then Sun 10th unrecorded
  const days=dailySeries(d);
  assert.deepEqual(days.filter(x=>x.rest).map(x=>x.date),['2027-01-06','2027-01-09']);
  const c=consistency(days,'2027-01-09');
  // Mon, Tue, Wed(rest), Thu, Fri, Sat(rest): the rest days bridge the study days, so one streak of 4.
  assert.deepEqual([c.recordedDays,c.restDays,c.currentStreak,c.longestStreak,c.longestBreak],[4,2,4,4,0]);
  assert.equal(consistency(days,'2027-01-10').currentStreak,0);   // the 10th has no record: breaks it
});

test('weekday profile averages over elapsed days including empty ones',()=>{
  const profile=weekdayProfile(dailySeries(data()),'2027-01-10');
  assert.deepEqual(profile,[2,4,0,1,4,0,0]);
});

test('plan adherence looks at planned days so far, planned-ahead at the rest',()=>{
  const adherence=planAdherence(dailySeries(data()),'2027-01-10');
  assert.deepEqual([adherence.plannedDays,adherence.keptDays,adherence.plannedHours,adherence.recordedOnPlannedDays],[2,1,5,2]);
  assert.equal(Math.round(adherence.ratio*100),40);
  assert.deepEqual(plannedAhead(data(),'2027-01-10'),{hours:2.5,days:1,perDay:2.5});
});

test('plan versus recorded covers the last days of the phase up to as-of, for one subject',()=>{
  const days=recentPlanVsRecorded(data(),'a','2027-01-07',3);
  assert.deepEqual(days,[{date:'2027-01-05',planned:2,recorded:3},{date:'2027-01-06',planned:0,recorded:0},{date:'2027-01-07',planned:0,recorded:1}]);
  assert.equal(recentPlanVsRecorded(data(),'a','2027-01-05').length,2);   // the phase began on the 4th
  assert.deepEqual(recentPlanVsRecorded(data(),'missing','2027-01-07'),[]);
});

test('the centered comparison uses calendar plans to date and includes study on unplanned days',()=>{
  const comparison=planDeviation(dailySeries(data()),'2027-01-10');
  assert.deepEqual([comparison.recorded,comparison.planned,comparison.delta],[11,5,6]);
  assert.ok(comparison.position>50);
  const short=planDeviation(dailySeries(data()),'2027-01-06');
  assert.deepEqual([short.recorded,short.planned,short.delta],[6,5,1]);
  assert.equal(short.tone,'success');
  assert.equal(short.position,52.5);
});

const comparisonDay=(date:string,planned:number,recorded:number):DayPoint=>({date,planned,recorded,bySubject:{},weekday:0,rest:false});

test('plan equality is centered, shortfalls move left, excess moves right, and missing plans are neutral',()=>{
  const at=(planned:number,recorded:number)=>planDeviation([comparisonDay(dates[0],planned,recorded)],dates[0]);
  assert.equal(at(10,10).position,50);
  assert.equal(at(10,5).position,37.5);
  assert.equal(at(5,10).position,62.5);
  assert.equal(at(10,0).position,25);
  assert.equal(at(0,10).position,75);
  assert.equal(at(0,10).tone,'neutral');
  assert.equal(at(0,0).position,50);
  assert.equal(at(0,0).tone,'neutral');
  assert.equal(planDeviation([],dates[0]).strength,0);
});

test('the twenty hour range clamps the marker and color intensity without losing the actual gap',()=>{
  const at=(recorded:number)=>planDeviation([comparisonDay(dates[0],40,recorded)],dates[0]);
  assert.deepEqual([at(20).position,at(20).strength,at(20).delta],[0,100,-20]);
  assert.deepEqual([at(60).position,at(60).strength,at(60).delta],[100,100,20]);
  assert.deepEqual([at(0).position,at(0).strength,at(0).delta],[0,100,-40]);
  assert.deepEqual([at(85).position,at(85).strength,at(85).delta],[100,100,45]);
  const elapsed=[comparisonDay(dates[0],40,45)];
  const extra=[...elapsed,comparisonDay(dates[1],100,0),comparisonDay('2027-01-03',0,0)];
  assert.deepEqual(planDeviation(extra,dates[0]),planDeviation(elapsed,dates[0]));
});

test('colors follow direction and deepen with hours rather than a percentage of the plan',()=>{
  const at=(recorded:number)=>planDeviation([comparisonDay(dates[0],20,recorded)],dates[0]);
  assert.equal(at(20).tone,'neutral');
  assert.equal(at(21).tone,'success');
  assert.equal(at(30).tone,'success');
  assert.equal(at(31).tone,'strong-success');
  assert.equal(at(19).tone,'warning');
  assert.equal(at(17).tone,'warning');
  assert.equal(at(10).tone,'warning');
  assert.equal(at(9).tone,'danger');
  assert.equal(at(18).strength,10);
  assert.equal(at(22).strength,10);
  const large=planDeviation([comparisonDay(dates[0],200,203)],dates[0]);
  assert.deepEqual([large.position,large.tone,large.strength],[at(23).position,at(23).tone,at(23).strength]);
});

test('course balance explains the percentage point gap and waits for recorded hours and targets',()=>{
  const comparison=balanceDelta(subjectStats(data(),'2027-01-10'))!;
  assert.equal(comparison.recordedShare,54.5);
  assert.equal(comparison.targetShare,66.7);
  const empty=data();
  empty.subjects=empty.subjects.map(s=>({...s,hours:{}}));
  assert.equal(balanceDelta(subjectStats(empty,'2027-01-10')),null);
  empty.subjects=data().subjects.map(s=>({...s,targetHours:0}));
  assert.equal(balanceDelta(subjectStats(empty,'2027-01-10')),null);
});
