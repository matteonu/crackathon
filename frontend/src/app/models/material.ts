export const MATERIAL_CATEGORIES = ['Slides','Notes','Transcripts','Books','Exams','Exercises'] as const;
export const MATERIAL_MARKERS = ['To read','Done','Revisit','Ignore'] as const;
export type MaterialCategory = typeof MATERIAL_CATEGORIES[number];
export type MaterialMarker = typeof MATERIAL_MARKERS[number];
export type MaterialKind = 'folder' | 'pdf' | 'md' | 'txt';
export type ToolId = 'summary' | 'flashcards';
export interface Flashcard { id?:string; question:string; answer:string; demo?:boolean; }
export interface ToolResult { text?: string; cards?: Flashcard[]; }
export interface Material {
  id:string; subjectId:string; name:string; size:number; category:MaterialCategory;
  marker:MaterialMarker; blob:Blob; added:number;
  kind?:MaterialKind; parentId?:string|null; description?:string; content?:string;
  outputs?:Partial<Record<ToolId,ToolResult>>;
}
export interface FolderCard extends Flashcard { key:string; fileId:string; fileName:string; }
export interface TreeRow { material:Material; depth:number; }

export function materialKind(file:Material):MaterialKind { return file.kind??'pdf'; }
export function normalizeMaterial(file:Material):Material {
  return {...file,kind:materialKind(file),parentId:file.parentId??null,description:file.description??'',
    outputs:{...file.outputs,flashcards:file.outputs?.flashcards?{...file.outputs.flashcards,cards:file.outputs.flashcards.cards?.map((card,i)=>({...card,id:card.id??`${file.id}-${i}`,demo:card.demo??true}))}:undefined}};
}
export function descendants(files:readonly Material[],parentId:string|null):Material[] {
  const found:Material[]=[];const visited=new Set<string>();
  function visit(parent:string|null):void {
    for(const file of files.filter(f=>(f.parentId??null)===parent)){
      if(visited.has(file.id))continue;visited.add(file.id);found.push(file);
      if(materialKind(file)==='folder')visit(file.id);
    }
  }
  visit(parentId);return found;
}
export function folderCards(files:readonly Material[],folderId:string|null):FolderCard[] {
  return descendants(files,folderId).filter(f=>materialKind(f)!=='folder').flatMap(file=>(file.outputs?.flashcards?.cards??[]).map((card,i)=>({...card,key:card.id??`${file.id}-${i}`,fileId:file.id,fileName:file.name})));
}
export function treeRows(files:readonly Material[],expanded:ReadonlySet<string>,query='',marker=''):TreeRow[] {
  const rows:TreeRow[]=[];const seen=new Set<string>();const filtering=!!query||!!marker;
  const matches=(f:Material)=>f.name.toLowerCase().includes(query.toLowerCase())&&(!marker||f.marker===marker);
  function visit(parent:string|null,depth:number):void {
    const children=files.filter(f=>(f.parentId??null)===parent).sort((a,b)=>Number(materialKind(b)==='folder')-Number(materialKind(a)==='folder')||a.name.localeCompare(b.name));
    for(const file of children){
      if(seen.has(file.id))continue;seen.add(file.id);
      const folder=materialKind(file)==='folder';
      if(filtering&&!matches(file)&&!(folder&&descendants(files,file.id).some(matches)))continue;
      rows.push({material:file,depth});
      if(folder&&(expanded.has(file.id)||filtering))visit(file.id,depth+1);
    }
  }
  visit(null,0);return rows;
}
export function validParent(files:readonly Material[],subjectId:string,parentId:string|null,id?:string):boolean {
  if(parentId===null)return true;
  const parent=files.find(f=>f.id===parentId&&f.subjectId===subjectId&&materialKind(f)==='folder');
  return !!parent&&parentId!==id&&(!id||!descendants(files,id).some(f=>f.id===parentId));
}
export function materialName(name:string,kind:MaterialKind):string {
  let value=name.trim();if(!value||value.length>180||/[\\/\x00-\x1f]/.test(value)||value==='.'||value==='..')throw new Error('Use a name of 1–180 characters, without slashes.');
  if(kind!=='folder'&&!value.toLowerCase().endsWith('.'+kind))value+='.'+kind;
  return value;
}
