export type Rating='again'|'hard'|'good'|'easy';
export interface RecallAnalytics {
  path:string[];name:string;label:string;priority:number;cards:number;reviews:number;mistakes:number;lapses:number;
  success_rate:number|null;due_cards:number;overdue_review_cards:number;mature_cards:number;
  average_interval_days:number;average_response_seconds:number|null;
  states:Record<'new'|'learning'|'review'|'relearning',number>;ratings:Record<Rating,number>;
}
export const recallKey=(path:readonly string[]):string=>JSON.stringify(path);

/** These categories partition the collection: mature, seen but not mature, unseen. */
export function recallSnapshot(row:RecallAnalytics){
  const mature=row.mature_cards,left=row.states.new,learned=row.cards-mature-left;
  return {mature,learned,left,total:row.cards,progress:row.cards?(mature+learned)/row.cards*100:0};
}

/** Keep descendants hidden until every ancestor is expanded, regardless of API row order. */
export function recallTreeRows(rows:readonly RecallAnalytics[],expanded:ReadonlySet<string>){
  const children=new Map<string,RecallAnalytics[]>();
  for(const row of rows){if(!row.path.length)continue;const parent=recallKey(row.path.slice(0,-1));children.set(parent,[...children.get(parent)??[],row]);}
  const visible:{row:RecallAnalytics;key:string;depth:number;hasChildren:boolean;snapshot:ReturnType<typeof recallSnapshot>}[]=[];
  const visit=(row:RecallAnalytics)=>{
    const key=recallKey(row.path),nested=children.get(key)??[];
    visible.push({row,key,depth:row.path.length,hasChildren:nested.length>0,snapshot:recallSnapshot(row)});
    if(expanded.has(key))for(const child of nested)visit(child);
  };
  for(const root of rows.filter(row=>!row.path.length))visit(root);
  return visible;
}
