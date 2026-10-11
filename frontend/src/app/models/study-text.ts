export type StudyTextPart={kind:'text';text:string}|{kind:'math';latex:string;source:string;display:boolean};

function escaped(text:string,index:number):boolean{
  let count=0;while(index>0&&text[--index]==='\\')count++;
  return count%2===1;
}

/** Only explicit, paired delimiters are math. Preserve prose, code and malformed
 * expressions verbatim; never guess that ordinary mathematical prose is TeX. */
export function splitStudyText(text:string):StudyTextPart[]{
  const parts:StudyTextPart[]=[];let plainStart=0,index=0;
  while(index<text.length){
    if(text[index]==='`'&&!escaped(text,index)){
      let end=index;while(text[end]==='`')end++;
      const fence=text.slice(index,end),closing=text.indexOf(fence,end);
      index=closing<0?text.length:closing+fence.length;continue;
    }
    if(escaped(text,index)){index++;continue;}
    let open='',close='',display=false;
    if(text.startsWith('\\[',index)){open='\\[';close='\\]';display=true;}
    else if(text.startsWith('\\(',index)){open='\\(';close='\\)';}
    else if(text.startsWith('$$',index)){open=close='$$';display=true;}
    else if(text[index]==='$'){open=close='$';}
    if(!open){index++;continue;}
    const start=index+open.length;let end=text.indexOf(close,start);
    while(end>=0&&escaped(text,end))end=text.indexOf(close,end+close.length);
    const latex=end<0?'':text.slice(start,end);
    // Single-dollar math cannot cross lines or use whitespace at its edges.
    // Reject a closing dollar followed by a digit (e.g. "$5 and $10").
    if(!latex.trim()||(open==='$'&&(/^[\s]|[\s]$|[\r\n]/.test(latex)||/\d/.test(text[end+1]??'')))){index+=open.length;continue;}
    if(index>plainStart)parts.push({kind:'text',text:text.slice(plainStart,index)});
    const next=end+close.length;
    parts.push({kind:'math',latex,source:text.slice(index,next),display});index=plainStart=next;
  }
  if(plainStart<text.length)parts.push({kind:'text',text:text.slice(plainStart)});
  return parts;
}

export const MATH_OPTIONS={trust:false,throwOnError:true,maxExpand:500,maxSize:10,strict:'ignore',output:'htmlAndMathml'} as const;
type RenderMath=(latex:string,options:typeof MATH_OPTIONS&{displayMode:boolean})=>string;

/** Keep rendered HTML only, bounded by both entry count and total characters. */
export class StudyMathCache {
  private readonly entries=new Map<string,string|null>();
  private characters=0;
  get size():number{return this.entries.size;}
  get totalCharacters():number{return this.characters;}
  render(latex:string,display:boolean,render:RenderMath):string|null{
    if(latex.length>8000)return null;
    const key=JSON.stringify([display,latex]);
    if(this.entries.has(key)){
      const cached=this.entries.get(key)!;this.entries.delete(key);this.entries.set(key,cached);return cached;
    }
    let html:string|null=null;
    try{html=render(latex,{...MATH_OPTIONS,displayMode:display});}catch{/* Caller displays original text. */}
    if((html?.length??0)>1_000_000)return null;
    this.entries.set(key,html);this.characters+=key.length+(html?.length??0);
    while(this.entries.size>128||this.characters>1_000_000){
      const oldest=this.entries.keys().next().value!;
      this.characters-=oldest.length+(this.entries.get(oldest)?.length??0);this.entries.delete(oldest);
    }
    return html;
  }
}
