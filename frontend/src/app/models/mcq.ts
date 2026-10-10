import { LearningMode } from './material';

export interface McqOption { id:string; text:string; }
export interface McqQuestion { id:string; prompt:string; selectionMode:'single'|'multiple'; options:McqOption[]; }
export interface McqScore { correct:number; total:number; }
export interface McqSet {
  id:string; documentId:string; mode:LearningMode; seriesId:string; version:number;
  status:'queued'|'running'|'complete'|'error'; questionCount:number; error?:string|null;
  requestedQuestionCount?:number|null;
  replacesId?:string|null; supersededById?:string|null; latestScore?:McqScore|null;
  activeSessionId?:string|null; questions?:McqQuestion[];
}
export interface McqSession {
  id:string; setId:string; status:'active'|'completed'; position:number; score:number; total:number; questions:McqQuestion[];
}
export interface McqAnswerResult {
  correct:boolean; correctOptionIds:string[]; explanation:string; sourcePages:number[]; session:McqSession;
}
