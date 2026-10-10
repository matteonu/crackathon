export const MATERIAL_CATEGORIES = ['Slides','Solutions','Scripts','Notes','Transcripts','Books','Exams','Exercises'] as const;
export const UPLOAD_CATEGORIES = ['Slides','Exercises','Solutions','Exams','Scripts'] as const;
export const MATERIAL_MARKERS = ['To read','Done','Revisit','Ignore'] as const;
export type MaterialCategory = typeof MATERIAL_CATEGORIES[number];
export type MaterialMarker = typeof MATERIAL_MARKERS[number];
export type MaterialKind = 'folder' | 'pdf' | 'md' | 'txt' | 'deck';
<<<<<<< HEAD
export type DocumentType = 'slides' | 'mock_exam' | 'exercise' | 'exercise_solution' | 'script' | 'summary' | 'cards' | 'mcq';
export const CATEGORY_DOCUMENT_TYPES:Partial<Record<MaterialCategory,DocumentType>> = {
  Slides:'slides', Exams:'mock_exam', Exercises:'exercise', Solutions:'exercise_solution', Scripts:'script'
};
const DOCUMENT_TYPE_LABELS:Record<DocumentType,string> = {
  slides:'slides', mock_exam:'exam', exercise:'exercise', exercise_solution:'exercise solution',
  script:'script', summary:'summary', cards:'flashcards', mcq:'multiple choice'
};
=======
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
export type ToolId = 'summary' | 'flashcards';
export interface Flashcard { id?:string; question:string; answer:string; demo?:boolean; generated?:boolean; }
export type LearningMode = 'shallow' | 'deep';
export type LearningTask = 'summary' | 'flashcards';
export interface ProcessingState { status:'queued'|'running'|'complete'|'error'; error?:string; mode?:LearningMode; requestedQuestions?:number; task?:LearningTask; }
export interface ToolResult { text?: string; cards?: Flashcard[]; }
export interface Material {
  id:string; subjectId:string; name:string; size:number; category:MaterialCategory;
  marker:MaterialMarker; added:number;
  /** Only while a newly chosen file is still being uploaded; the server is the source. */
  blob?:Blob;
<<<<<<< HEAD
  kind?:MaterialKind; type?:DocumentType|null; parentId?:string|null; description?:string; content?:string;
=======
  kind?:MaterialKind; parentId?:string|null; description?:string; content?:string;
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
  sourcePdfId?:string|null;generationMode?:LearningMode|null;folderWeight?:number;
  outputs?:Partial<Record<ToolId,ToolResult>>;
  processing?:ProcessingState;
}
export interface FolderCard extends Flashcard { key:string; fileId:string; fileName:string; deckId?:string; }
export interface TreeRow { material:Material; depth:number; }

export function materialKind(file:Material):MaterialKind { return file.kind??'pdf'; }
export function materialType(file:Material):DocumentType|null {
  if(materialKind(file)==='folder')return null;
  return file.type===undefined?(CATEGORY_DOCUMENT_TYPES[file.category]??null):file.type;
}
export function materialTypeLabel(file:Material):string {
  const type=materialType(file);
  return type?DOCUMENT_TYPE_LABELS[type]:file.category.toLowerCase();
}
export function canGenerateFlashcards(file:Material):boolean { return materialKind(file)==='pdf'&&['slides','exercise_solution','script'].includes(materialType(file)??''); }
/** Where the server serves this file's bytes: the PDF itself, or a text file's content. */
export function materialFileUrl(id:string):string { return `/api/materials/${encodeURIComponent(id)}/file`; }
export function normalizeMaterial(file:Material):Material {
  return {...file,kind:materialKind(file),type:materialType(file),parentId:file.parentId??null,description:file.description??'',
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
<<<<<<< HEAD
  return descendants(files,folderId).filter(f=>materialKind(f)!=='folder'&&(materialKind(f)!=='pdf'||canGenerateFlashcards(f))).flatMap(file=>(file.outputs?.flashcards?.cards??[]).map((card,i)=>({...card,key:card.id??`${file.id}-${i}`,fileId:file.sourcePdfId??file.id,fileName:file.name,deckId:materialKind(file)==='deck'?file.id:undefined})));
=======
  return descendants(files,folderId).filter(f=>materialKind(f)!=='folder').flatMap(file=>(file.outputs?.flashcards?.cards??[]).map((card,i)=>({...card,key:card.id??`${file.id}-${i}`,fileId:file.sourcePdfId??file.id,fileName:file.name,deckId:materialKind(file)==='deck'?file.id:undefined})));
>>>>>>> 08e7f8f77946891bcf932333d6d2f8c785987ee0
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
  if(!['folder','deck'].includes(kind)&&!value.toLowerCase().endsWith('.'+kind))value+='.'+kind;
  return value;
}
