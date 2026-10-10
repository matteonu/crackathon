export interface PagePosition { page:number; top:number; bottom:number; }
/** Prefer the page occupying most of the viewport; its neighbours form the context. */
export function visiblePdfPage(pages:readonly PagePosition[],top:number,bottom:number):number|null {
  let selected:number|null=null;let largest=0;
  for(const page of pages){
    const overlap=Math.max(0,Math.min(page.bottom,bottom)-Math.max(page.top,top));
    if(overlap>largest){largest=overlap;selected=page.page;}
  }
  return selected;
}
export function contextPages(page:number,total:number):number[] {
  if(!Number.isInteger(page)||page<1||page>total)return [];
  return Array.from({length:Math.min(total,page+1)-Math.max(1,page-1)+1},(_,i)=>Math.max(1,page-1)+i);
}
