import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { StudyStore } from '../services/study-store';
import { ScrollButtonsComponent } from '../shared/scroll-buttons.component';
import { WEEKDAYS, asOfDate, balanceDelta, consistency, dailySeries, pace, planAdherence, planDeviation, plannedAhead, subjectStats, weekdayProfile, weeklySeries } from '../models/analytics';

const DAY_W = 18, CHART_H = 150, PAD_L = 34, PAD_B = 26, PAD_T = 18;

/** Schedule statistics for the analytics page: pace, consistency, plan adherence, and the charts
 *  behind them. Every number comes from models/analytics.ts; this component only lays them out. */
@Component({selector:'app-schedule-stats',standalone:true,imports:[RouterLink,ScrollButtonsComponent],template:`
  <section class="panel stats-panel stats-summary-panel" aria-labelledby="pace-title">
    <div class="panel-heading"><div><div class="section-label">SCHEDULE STATISTICS</div><h2 id="pace-title">Study time at a glance</h2><p>{{phaseLabel()}} · as of {{dayLabel(asOf())}} · {{pace().elapsedDays}} of {{pace().totalDays}} days</p></div><span class="soft-badge schedule-plan-badge" [attr.data-tone]="deviation().tone">{{planGapLabel()}}</span></div>
    <div class="stat-tiles">
      <article class="stat-tile" tabindex="0" aria-labelledby="hours-stat-title" aria-describedby="hours-stat-detail">
        <h3 class="eyebrow" id="hours-stat-title">Hours vs. plan</h3>
        <div class="hero-metric stat-number">{{deviation().recorded}}<span class="stat-unit">h</span></div>
        <div class="stat-context">
          <div class="deviation-chart" role="img" [attr.aria-label]="deviationLabel()" [attr.data-tone]="deviation().tone" [style.--deviation-strength]="deviation().strength+'%'">
            <div class="deviation-track"><span class="deviation-fill" [style.left.%]="min(50,deviation().position)" [style.width.%]="abs(deviation().position-50)"></span><span class="deviation-midpoint"></span><span class="deviation-marker" [style.left.%]="deviation().position"></span></div>
            <div class="deviation-axis" aria-hidden="true"><span></span><span>{{deviation().planned}}h planned</span><span></span></div>
          </div>
          <span class="stat-context-summary">{{deviation().planned}} h planned by now</span>
        </div>
        <p class="stat-detail" id="hours-stat-detail">@if(deviation().planned===0){No planned hours yet.}@else if(deviation().delta===0){You are on schedule.}@else{You are <strong>{{abs(deviation().delta)}}</strong> {{deviation().delta<0?'behind':'ahead of'}} schedule.}</p>
      </article>
      <article class="stat-tile" tabindex="0" aria-labelledby="daily-stat-title" aria-describedby="daily-stat-detail">
        <h3 class="eyebrow" id="daily-stat-title">Daily hours to reach goal</h3>
        <div class="hero-metric stat-number">{{pace().neededPerDay}}<span class="stat-unit">h/day</span></div>
        <div class="stat-context"><span class="stat-context-summary">{{pace().remainingDays}} days remaining</span></div>
        <p class="stat-detail" id="daily-stat-detail">Hours needed each day to reach your {{pace().target}} h goal. Your average so far is <strong>{{pace().ratePerDay}} h/day</strong>.</p>
      </article>
      <article class="stat-tile" tabindex="0" aria-labelledby="days-stat-title" aria-describedby="days-stat-detail">
        <h3 class="eyebrow" id="days-stat-title">Days you studied</h3>
        <div class="hero-metric stat-number">{{consistency().recordedDays}}<span class="stat-unit">days</span></div>
        <div class="stat-context"><span class="stat-context-summary">Out of {{consistency().elapsedDays}} days so far</span></div>
        <p class="stat-detail" id="days-stat-detail">Your current streak is <strong>{{consistency().currentStreak}} days</strong>; your longest is <strong>{{consistency().longestStreak}}</strong>. A typical study day is {{consistency().medianPerRecordedDay}} h.@if(consistency().restDays){ {{consistency().restDays}} recorded rest {{consistency().restDays===1?'day keeps':'days keep'}} your streak.}</p>
      </article>
      <article class="stat-tile" tabindex="0" aria-labelledby="kept-stat-title" aria-describedby="kept-stat-detail">
        <h3 class="eyebrow" id="kept-stat-title">Planned hours completed</h3>
        <div class="hero-metric stat-number">{{percent(adherence().ratio)}}<span class="stat-unit stat-percent">%</span></div>
        <div class="stat-context"><span class="stat-context-summary">{{adherence().recordedOnPlannedDays}} of {{adherence().plannedHours}} h completed</span></div>
        <p class="stat-detail" id="kept-stat-detail">The share of planned hours you recorded on their planned day. Extra hours do not increase this percentage. Your calendar has <strong>{{ahead().hours}} h</strong> planned after this date.</p>
      </article>
      <article class="stat-tile" tabindex="0" aria-labelledby="balance-stat-title" aria-describedby="balance-stat-detail">
        <h3 class="eyebrow" id="balance-stat-title">Course time imbalance</h3>
        @if(balance();as b){
          <div class="hero-metric stat-number">{{b.delta>0?'+':''}}{{b.delta}}<span class="stat-unit" title="Percentage points">pp</span></div>
          <div class="stat-context"><span class="stat-course"><i class="subject-dot" [style.background]="b.subject.color" aria-hidden="true"></i><span>{{b.subject.shortName}}</span></span><span class="stat-context-summary">{{b.delta>0?'Above':b.delta<0?'Below':'At'}} its target share</span></div>
          <p class="stat-detail" id="balance-stat-detail"><strong>{{b.subject.shortName}}</strong> takes {{b.recordedShare}}% of your recorded time, compared with {{b.targetShare}}% of the goal. This is the largest course gap, measured in percentage points.</p>
        }@else{
          <div class="hero-metric stat-number">—</div>
          <div class="stat-context"><span class="stat-context-summary">No comparison yet</span></div>
          <p class="stat-detail" id="balance-stat-detail">Record study hours for courses with a target to compare how you split your time.</p>
        }
      </article>
    </div>
  </section>

  <section class="panel stats-panel" aria-labelledby="daily-title">
    <div class="panel-heading"><div><h2 id="daily-title">Hours per day</h2><p>Recorded hours stacked by subject; planned sessions outlined; exams flagged.</p></div><app-scroll-buttons [target]="dailyViewport" label="daily hours" /></div>
    <div class="chart-legend">@for(s of store.subjects();track s.id){<span><i [style.background]="s.color"></i>{{s.shortName}}</span>}<span><i class="legend-planned"></i>Planned</span><span><i class="legend-asof"></i>As of</span></div>
    <div #dailyViewport class="horizontal-scroll chart-scroll" tabindex="0" role="region" aria-label="Hours per day, scroll horizontally">
      <svg class="chart" [attr.viewBox]="'0 0 '+dailyWidth()+' '+chartHeight" [attr.width]="dailyWidth()" [attr.height]="chartHeight" role="img" [attr.aria-label]="'Hours per day from '+store.dates()[0]+' to '+store.dates()[store.dates().length-1]">
        @for(tick of yTicks(dailyMax());track tick){<line class="grid" [attr.x1]="padL" [attr.x2]="dailyWidth()" [attr.y1]="yScale(tick,dailyMax())" [attr.y2]="yScale(tick,dailyMax())" /><text class="axis" [attr.x]="padL-6" [attr.y]="yScale(tick,dailyMax())+3" text-anchor="end">{{tick}}</text>}
        @for(day of days();track day.date;let i=$index){
          @if(day.planned>0){<rect class="planned" [attr.x]="padL+i*dayW+3" [attr.y]="yScale(day.planned,dailyMax())" [attr.width]="dayW-6" [attr.height]="yScale(0,dailyMax())-yScale(day.planned,dailyMax())" rx="2"><title>{{dayLabel(day.date)}}: {{day.planned}} h planned</title></rect>}
          @for(seg of stack(day);track seg.id){<rect [attr.fill]="seg.color" [attr.x]="padL+i*dayW+3" [attr.y]="yScale(seg.top,dailyMax())" [attr.width]="dayW-6" [attr.height]="max(0,yScale(seg.bottom,dailyMax())-yScale(seg.top,dailyMax())-1)" [attr.rx]="seg.last?2:0"><title>{{dayLabel(day.date)}}: {{seg.name}} {{seg.hours}} h (day total {{day.recorded}} h)</title></rect>}
          @if(day.weekday===0||i===0){<text class="axis" [attr.x]="padL+i*dayW+dayW/2" [attr.y]="chartHeight-8" text-anchor="middle">{{shortDate(day.date)}}</text>}
        }
        @for(s of store.subjects();track s.id){@if(dayIndex(s.examDate)>=0){<g class="exam"><line [attr.x1]="padL+dayIndex(s.examDate)*dayW+dayW/2" [attr.x2]="padL+dayIndex(s.examDate)*dayW+dayW/2" [attr.y1]="padT-6" [attr.y2]="yScale(0,dailyMax())" [attr.stroke]="s.color" /><circle [attr.cx]="padL+dayIndex(s.examDate)*dayW+dayW/2" [attr.cy]="padT-6" r="3.5" [attr.fill]="s.color"><title>{{s.shortName}} exam · {{dayLabel(s.examDate)}}</title></circle></g>}}
        <line class="asof" [attr.x1]="padL+(dayIndex(asOf())+1)*dayW" [attr.x2]="padL+(dayIndex(asOf())+1)*dayW" [attr.y1]="padT-10" [attr.y2]="yScale(0,dailyMax())" />
        <line class="baseline" [attr.x1]="padL" [attr.x2]="dailyWidth()" [attr.y1]="yScale(0,dailyMax())" [attr.y2]="yScale(0,dailyMax())" />
      </svg>
    </div>
  </section>

  <div class="stats-grid">
    <section class="panel stats-panel" aria-labelledby="cumulative-title">
      <div class="panel-heading"><div><h2 id="cumulative-title">Total hours over time</h2><p>Cumulative recorded hours against the line that reaches the target on the last day.</p></div></div>
      <svg class="chart" [attr.viewBox]="'0 0 '+smallW+' '+chartHeight" preserveAspectRatio="none" role="img" aria-label="Cumulative hours versus an even pace">
        @for(tick of yTicks(pace().target);track tick){<line class="grid" [attr.x1]="padL" [attr.x2]="smallW" [attr.y1]="yScale(tick,pace().target)" [attr.y2]="yScale(tick,pace().target)" /><text class="axis" [attr.x]="padL-6" [attr.y]="yScale(tick,pace().target)+3" text-anchor="end">{{tick}}</text>}
        <line class="pace-line" [attr.x1]="padL" [attr.x2]="smallW" [attr.y1]="yScale(0,pace().target)" [attr.y2]="yScale(pace().target,pace().target)" />
        <path class="cumulative-area" [attr.d]="cumulativeArea()" /><path class="cumulative-line" [attr.d]="cumulativePath()" />
        <circle class="cumulative-end" [attr.cx]="xSmall(dayIndex(asOf()))" [attr.cy]="yScale(pace().recorded,pace().target)" r="4"><title>{{pace().recorded}} h by {{dayLabel(asOf())}}</title></circle>
        <text class="label" [attr.x]="xSmall(dayIndex(asOf()))+(dayIndex(asOf())>store.dates().length*0.6?-8:8)" [attr.y]="yScale(pace().recorded,pace().target)-8" [attr.text-anchor]="dayIndex(asOf())>store.dates().length*0.6?'end':'start'">{{pace().recorded}} h</text>
        <text class="axis" [attr.x]="padL" [attr.y]="chartHeight-8">{{shortDate(store.dates()[0])}}</text><text class="axis" [attr.x]="smallW" [attr.y]="chartHeight-8" text-anchor="end">{{shortDate(store.dates()[store.dates().length-1])}}</text>
      </svg>
      <div class="chart-legend"><span><i style="background:var(--green)"></i>Recorded</span><span><i class="legend-pace"></i>Even pace to {{pace().target}} h</span></div>
    </section>

    <section class="panel stats-panel" aria-labelledby="week-title">
      <div class="panel-heading"><div><h2 id="week-title">Hours each week</h2><p>Recorded, planned, and the weekly share of the target.</p></div></div>
      <svg class="chart" [attr.viewBox]="'0 0 '+smallW+' '+chartHeight" preserveAspectRatio="none" role="img" aria-label="Hours per week">
        @for(tick of yTicks(weekMax());track tick){<line class="grid" [attr.x1]="padL" [attr.x2]="smallW" [attr.y1]="yScale(tick,weekMax())" [attr.y2]="yScale(tick,weekMax())" /><text class="axis" [attr.x]="padL-6" [attr.y]="yScale(tick,weekMax())+3" text-anchor="end">{{tick}}</text>}
        @for(w of weeks();track w.start;let i=$index){
          <rect class="planned" [attr.x]="xWeek(i)+weekSlot()*0.5" [attr.y]="yScale(w.planned,weekMax())" [attr.width]="weekSlot()*0.3" [attr.height]="yScale(0,weekMax())-yScale(w.planned,weekMax())" rx="2"><title>Week of {{dayLabel(w.start)}}: {{w.planned}} h planned</title></rect>
          <rect class="recorded" [attr.x]="xWeek(i)+weekSlot()*0.15" [attr.y]="yScale(w.recorded,weekMax())" [attr.width]="weekSlot()*0.3" [attr.height]="yScale(0,weekMax())-yScale(w.recorded,weekMax())" rx="2"><title>Week of {{dayLabel(w.start)}}: {{w.recorded}} h recorded</title></rect>
          <line class="target-tick" [attr.x1]="xWeek(i)+weekSlot()*0.1" [attr.x2]="xWeek(i)+weekSlot()*0.9" [attr.y1]="yScale(w.target,weekMax())" [attr.y2]="yScale(w.target,weekMax())"><title>Target share {{w.target}} h</title></line>
          @if(i%weekLabelEvery()===0){<text class="axis" [attr.x]="xWeek(i)+weekSlot()/2" [attr.y]="chartHeight-8" text-anchor="middle">{{shortDate(w.start)}}</text>}
        }
        <line class="baseline" [attr.x1]="padL" [attr.x2]="smallW" [attr.y1]="yScale(0,weekMax())" [attr.y2]="yScale(0,weekMax())" />
      </svg>
      <div class="chart-legend"><span><i style="background:var(--green)"></i>Recorded</span><span><i class="legend-planned"></i>Planned</span><span><i class="legend-target"></i>Target share</span></div>
    </section>

    <section class="panel stats-panel" aria-labelledby="weekday-title">
      <div class="panel-heading"><div><h2 id="weekday-title">Average hours by weekday</h2><p>Mean recorded hours per weekday so far. Empty days count.</p></div></div>
      <svg class="chart" [attr.viewBox]="'0 0 '+smallW+' '+chartHeight" preserveAspectRatio="none" role="img" aria-label="Average hours per weekday">
        @for(tick of yTicks(profileMax());track tick){<line class="grid" [attr.x1]="padL" [attr.x2]="smallW" [attr.y1]="yScale(tick,profileMax())" [attr.y2]="yScale(tick,profileMax())" /><text class="axis" [attr.x]="padL-6" [attr.y]="yScale(tick,profileMax())+3" text-anchor="end">{{tick}}</text>}
        @for(h of profile();track $index;let i=$index){
          <rect class="recorded" [class.dim]="h<profileMax()*0.5" [attr.x]="xDay7(i)+daySlot()*0.2" [attr.y]="yScale(h,profileMax())" [attr.width]="daySlot()*0.6" [attr.height]="yScale(0,profileMax())-yScale(h,profileMax())" rx="3"><title>{{weekdays[i]}}: {{h}} h on average</title></rect>
          <text class="label" [attr.x]="xDay7(i)+daySlot()/2" [attr.y]="yScale(h,profileMax())-5" text-anchor="middle">{{h}}</text>
          <text class="axis" [attr.x]="xDay7(i)+daySlot()/2" [attr.y]="chartHeight-8" text-anchor="middle">{{weekdays[i]}}</text>
        }
        <line class="baseline" [attr.x1]="padL" [attr.x2]="smallW" [attr.y1]="yScale(0,profileMax())" [attr.y2]="yScale(0,profileMax())" />
      </svg>
      @if(consistency().bestDay;as best){<p class="chart-note">Best day so far: <strong>{{best.recorded}} h</strong> on {{dayLabel(best.date)}}.</p>}
    </section>
  </div>

  <section class="panel stats-panel" aria-labelledby="subjects-title">
    <div class="panel-heading"><div><h2 id="subjects-title">Study goals by course</h2><p>What is left and what that means per day until the exam.</p></div><app-scroll-buttons [target]="subjectViewport" label="subject table" /></div>
    <div #subjectViewport class="horizontal-scroll" tabindex="0" role="region" aria-label="Per-subject statistics, scroll horizontally">
      <table class="stats-table"><thead><tr><th>Subject</th><th>Progress</th><th>Recorded</th><th>Left</th><th>Exam</th><th>Days</th><th>Needed</th><th>Planned</th><th>Status</th></tr></thead><tbody>
        @for(s of subjects();track s.subject.id){<tr>
          <th scope="row"><a [routerLink]="['/subject-tab',s.subject.id]"><i class="subject-dot" [style.background]="s.subject.color"></i>{{s.subject.shortName}}</a></th>
          <td><div class="bar-track wide"><i [style.background]="s.subject.color" [style.width.%]="s.percent"></i></div></td>
          <td>{{s.recorded}} h</td><td>{{s.remaining}} h</td><td>{{dayLabel(s.subject.examDate)}}</td><td>{{s.daysToExam}}</td>
          <td>{{neededLabel(s.neededPerDay)}}</td><td>{{s.plannedAhead}} h</td>
          <td><span class="stat-pill" [class]="'stat-pill '+s.status">{{statusLabel(s.status)}}</span></td>
        </tr>}
      </tbody></table>
    </div>
  </section>
`})
export class ScheduleStatsComponent {
  readonly store=inject(StudyStore);
  readonly dayW=DAY_W;readonly chartHeight=CHART_H;readonly padL=PAD_L;readonly padT=PAD_T;readonly smallW=360;readonly weekdays=WEEKDAYS;
  readonly min=Math.min;readonly max=Math.max;readonly abs=Math.abs;
  readonly asOf=computed(()=>asOfDate(this.store.data(),today()));
  readonly days=computed(()=>dailySeries(this.store.data()));
  readonly weeks=computed(()=>weeklySeries(this.store.data(),this.days()));
  readonly pace=computed(()=>pace(this.store.data(),this.asOf()));
  readonly subjects=computed(()=>subjectStats(this.store.data(),this.asOf()));
  readonly consistency=computed(()=>consistency(this.days(),this.asOf()));
  readonly profile=computed(()=>weekdayProfile(this.days(),this.asOf()));
  readonly deviation=computed(()=>planDeviation(this.days(),this.asOf()));
  readonly adherence=computed(()=>planAdherence(this.days(),this.asOf()));
  readonly ahead=computed(()=>plannedAhead(this.store.data(),this.asOf()));
  readonly balance=computed(()=>balanceDelta(this.subjects()));
  readonly dailyMax=computed(()=>Math.max(2,...this.days().map(d=>Math.max(d.recorded,d.planned))));
  readonly weekMax=computed(()=>Math.max(2,...this.weeks().map(w=>Math.max(w.recorded,w.planned,w.target))));
  readonly profileMax=computed(()=>Math.max(1,...this.profile()));
  readonly dailyWidth=computed(()=>PAD_L+this.days().length*DAY_W+8);
  readonly weekSlot=computed(()=>(this.smallW-PAD_L)/Math.max(1,this.weeks().length));
  readonly weekLabelEvery=computed(()=>Math.max(1,Math.ceil(this.weeks().length/7)));   // at most ~7 week labels
  readonly daySlot=computed(()=>(this.smallW-PAD_L)/7);
  readonly phaseLabel=computed(()=>`${this.store.data().semester} study phase`);
  readonly planGapLabel=computed(()=>{const d=this.deviation();return d.planned===0?'No planned hours yet':d.delta===0?'On plan':`${Math.abs(d.delta)} h ${d.delta>0?'ahead of':'behind'} plan`;});
  readonly deviationLabel=computed(()=>`${this.deviation().recorded} hours recorded versus ${this.deviation().planned} planned. ${this.planGapLabel()}. Scale: minus 20 to plus 20 hours; larger gaps stay at the ends.`);
  readonly cumulativePath=computed(()=>this.cumulativePoints().map((p,i)=>`${i?'L':'M'}${p[0]} ${p[1]}`).join(' '));
  readonly cumulativeArea=computed(()=>{const pts=this.cumulativePoints();if(!pts.length)return '';const base=this.yScale(0,this.pace().target);return `${this.cumulativePath()} L${pts[pts.length-1][0]} ${base} L${pts[0][0]} ${base} Z`;});
  private cumulativePoints():[number,number][]{
    const target=this.pace().target;let sum=0;const points:[number,number][]=[[this.xSmall(-1),this.yScale(0,target)]];
    this.days().forEach((d,i)=>{if(d.date<=this.asOf()){sum+=d.recorded;points.push([this.xSmall(i),this.yScale(sum,target)]);}});
    return points;
  }
  yScale(value:number,maxValue:number):number {return PAD_T+(1-Math.min(value,maxValue)/Math.max(maxValue,0.01))*(CHART_H-PAD_T-PAD_B);}
  /** At most six gridlines at a round step (1, 2, 5, 10, 20, 50, ...). */
  yTicks(maxValue:number):number[]{
    const raw=Math.max(maxValue,1)/5;const magnitude=10**Math.floor(Math.log10(raw));const step=[1,2,5,10].map(m=>m*magnitude).find(m=>m>=raw)??10*magnitude;
    const ticks=[];for(let v=0;v<=maxValue+1e-9;v+=step)ticks.push(Math.round(v*100)/100);return ticks;
  }
  xSmall(dayIndex:number):number {return PAD_L+(dayIndex+1)/Math.max(1,this.days().length)*(this.smallW-PAD_L);}
  xWeek(i:number):number {return PAD_L+i*this.weekSlot();}
  xDay7(i:number):number {return PAD_L+i*this.daySlot();}
  dayIndex(date:string):number {return this.store.dates().indexOf(date);}
  stack(day:{bySubject:Record<string,number>}):{id:string;name:string;color:string;hours:number;bottom:number;top:number;last:boolean}[]{
    const segments=[];let acc=0;const entries=this.store.subjects().filter(s=>day.bySubject[s.id]);
    for(const [i,s] of entries.entries()){const h=day.bySubject[s.id];segments.push({id:s.id,name:s.shortName,color:s.color,hours:h,bottom:acc,top:acc+h,last:i===entries.length-1});acc+=h;}
    return segments;
  }
  percent(ratio:number):number {return Math.round(ratio*100);}
  neededLabel(perDay:number):string {return Number.isFinite(perDay)?`${perDay} h/day`:'—';}
  statusLabel(status:string):string {return {done:'Done','on-track':'On track',behind:'Behind','at-risk':'At risk'}[status]??status;}
  dayLabel(iso:string):string {return new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(iso+'T12:00:00Z'));}
  shortDate(iso:string):string {return new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'numeric',timeZone:'UTC'}).format(new Date(iso+'T12:00:00Z'));}
}

function today():string {const n=new Date();return `${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}-${String(n.getDate()).padStart(2,'0')}`;}
