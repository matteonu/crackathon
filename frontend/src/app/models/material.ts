export const MATERIAL_CATEGORIES = ['Slides','Notes','Transcripts','Books','Exams','Exercises'] as const;
export const MATERIAL_MARKERS = ['To read','Done','Revisit','Ignore'] as const;
export type MaterialCategory = typeof MATERIAL_CATEGORIES[number];
export type MaterialMarker = typeof MATERIAL_MARKERS[number];
export type ToolId = 'summary' | 'flashcards';
export interface ToolResult { text?: string; cards?: {question:string;answer:string}[]; }
export interface Material {
  id:string; subjectId:string; name:string; size:number; category:MaterialCategory;
  marker:MaterialMarker; blob:Blob; added:number;
  outputs?:Partial<Record<ToolId,ToolResult>>;
}
