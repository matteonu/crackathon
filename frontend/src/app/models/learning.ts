import type { Flashcard, Material, ProcessingState, LearningMode, LearningTask } from './material.ts';

export interface StudyDocument {
  abstract?: string;
  sentence_count?: number;
  requested_sentences?: number;
  questions?: { question: string; answer: string; source_pdf?:string; source_pdf_id?:string; source_pages?:number[]; evidence?:string }[];
  complete?: boolean;
}

export interface StudyResult {
  id: string;
  mode?: LearningMode;
  task?: LearningTask;
  requested_questions?: number;
  status: ProcessingState['status'];
  error?: string;
  documents: StudyDocument[];
}

export function parseStudyResult(value: unknown, id: string, mode: LearningMode = 'shallow', task: LearningTask = 'flashcards'): StudyResult {
  const result = value as StudyResult;
  if (!result || result.id !== id || !['queued', 'running', 'complete', 'error'].includes(result.status)
      || !Array.isArray(result.documents) || result.documents.length > 1) {
    throw new Error('The Python server returned an invalid result file. Retry processing.');
  }
  if (result.error !== undefined && typeof result.error !== 'string') throw new Error('Invalid processing error.');
  if ((result.task ?? 'flashcards') !== task) throw new Error('The result belongs to a different processing task.');
  if (result.requested_questions !== undefined && (task === 'summary' ? result.requested_questions !== 0 : (!Number.isInteger(result.requested_questions) || result.requested_questions < 5 || result.requested_questions > 300))) throw new Error('Invalid flashcard count.');
  if ((result.mode ?? 'shallow') !== mode) throw new Error('The result belongs to a different processing mode. Retry processing.');
  for (const document of result.documents) {
    if (!document || typeof document !== 'object'
        || (document.abstract !== undefined && (typeof document.abstract !== 'string' || !document.abstract.trim()))
        || (document.questions !== undefined && (!Array.isArray(document.questions)
          || document.questions.some(card => !card || typeof card.question !== 'string' || !card.question.trim()
            || typeof card.answer !== 'string' || !card.answer.trim()
            || (card.source_pages !== undefined && (!Array.isArray(card.source_pages) || !card.source_pages.length
              || card.source_pages.some(page=>!Number.isInteger(page)||page<1) || typeof card.evidence!=='string'||!card.evidence.trim())))))) {
      throw new Error('The saved summary or flashcards are invalid. Retry processing.');
    }
  }
  if (task === 'summary' && result.documents.some(document => document.questions?.length)) throw new Error('A summary result must not contain flashcards.');
  if (result.status === 'complete' && (!result.documents[0]?.abstract || (task === 'flashcards' && !result.documents[0]?.questions?.length)
      || result.documents[0]?.sentence_count !== 1 || result.documents[0]?.complete !== true)) {
    throw new Error('The result file is missing its one-sentence summary or flashcards. Retry processing.');
  }
  return result;
}

/** Stable generated IDs replace old demo/generated cards while preserving manual cards. */
export function learningPatch(file: Material, result: StudyResult) {
  const document = result.documents[0];
  const task = result.task ?? 'flashcards';
  const summary = document?.abstract ?? file.outputs?.summary?.text ?? file.description ?? '';
  const manual = (file.outputs?.flashcards?.cards ?? []).filter(card => !card.demo && !card.generated);
  const generated: Flashcard[] = (document?.questions ?? []).map((card, index) => ({
    ...card, id: `pipeline:${file.id}:${index}`, demo: false, generated: true,
    ...(card.source_pages?.length&&card.evidence?{source:{pdfId:file.id,pdfName:file.name,pages:card.source_pages,evidence:card.evidence}}:{}),
  }));
  return {
    processing: { status: result.status, error: result.error ?? '', mode: result.mode ?? 'shallow', task,
      requestedQuestions: task === 'summary' ? (file.processing?.requestedQuestions || 60) : result.requested_questions ?? file.processing?.requestedQuestions ?? 60 },
    description: summary,
    outputs: {
      summary: { text: summary },
      flashcards: { cards: task === 'summary' ? (file.outputs?.flashcards?.cards ?? []) : [...generated, ...manual] },
    },
  };
}
