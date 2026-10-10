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
  id:string; setId:string; status:'active'|'completed'; position:number; score:number; total:number;
  createdAt:string; completedAt?:string|null; questions?:McqQuestion[]; answers?:McqSessionAnswer[];
}
export interface McqSessionAnswer {
  questionId:string; selectedOptionIds:string[]; correct:boolean; correctOptionIds:string[]; explanation:string; sourcePages:number[];
}
export interface McqAnswerResult {
  correct:boolean; correctOptionIds:string[]; explanation:string; sourcePages:number[]; session:McqSession;
}
