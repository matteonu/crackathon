import type { Flashcard } from './material';

// Imported from SudyhubPresentation-features cards.apkg.zip, in Anki card order.
// Source links are rebound to the uploaded PDF by demoFlashcards().
const FINAL_SLIDES_CARDS = [
  {
    "id": "demo-final-204749610734934",
    "question": "What broad learning needs does StudyHub’s Moodle with Benefits pillar address?",
    "answer": "It addresses organizing course materials, understanding lecture content, and reviewing what has been learned.",
    "pages": [
      4
    ]
  },
  {
    "id": "demo-final-234773067463689",
    "question": "How does StudyHub’s planning support connect longer-term preparation with weekly study?",
    "answer": "It supports semester and exam preparation as well as the generation of weekly study plans.",
    "pages": [
      6,
      7
    ]
  },
  {
    "id": "demo-final-245780264450566",
    "question": "What decision is StudyHub’s course progress tracking intended to support?",
    "answer": "It helps learners decide which course needs their attention.",
    "pages": [
      5
    ]
  },
  {
    "id": "demo-final-267401452462294",
    "question": "How do StudyHub’s planning and data-improvement pillars differ in focus?",
    "answer": "The planning pillar organizes study schedules, while the data-improvement pillar uses learning insights to support better study habits.",
    "pages": [
      6,
      8
    ]
  },
  {
    "id": "demo-final-92242595679065",
    "question": "How does StudyHub help a learner resolve a question about lecture content?",
    "answer": "It provides context-aware AI explanations in response to questions about the lecture materials.",
    "pages": [
      4,
      5
    ]
  },
  {
    "id": "demo-final-247710925503639",
    "question": "How does StudyHub identify weak areas in a learner’s studies?",
    "answer": "It uses lecture material coverage and Anki statistics to identify weak areas.",
    "pages": [
      9
    ]
  },
  {
    "id": "demo-final-79209319569634",
    "question": "How does StudyHub connect activity tracking with study-plan monitoring?",
    "answer": "It tracks study activity and shows whether the learner is on track with the study plan.",
    "pages": [
      9
    ]
  },
  {
    "id": "demo-final-141134240461889",
    "question": "How does StudyHub make completed coursework visible to the learner?",
    "answer": "It provides material-coverage insights showing completed items such as slides and exercises.",
    "pages": [
      5
    ]
  },
  {
    "id": "demo-final-5423916827",
    "question": "How does StudyHub bring study commitments and time off into a single planning view?",
    "answer": "It provides an overview containing tasks with deadlines, days off, and exams.",
    "pages": [
      7
    ]
  },
  {
    "id": "demo-final-221756609377456",
    "question": "What time interval is explicitly specified for StudyHub’s generated study plan?",
    "answer": "The generated study plan is weekly.",
    "pages": [
      7
    ]
  },
  {
    "id": "demo-final-164256281467980",
    "question": "What degree of customization is stated for StudyHub’s study-plan generation?",
    "answer": "Study-plan generation is described as fully customizable.",
    "pages": [
      7
    ]
  },
  {
    "id": "demo-final-203542154069864",
    "question": "Why might StudyHub reduce the need to switch locations when accessing course documents?",
    "answer": "Inference: If the learner uploads the needed documents, keeping them in one place could reduce switching between separate storage locations.",
    "pages": [
      4,
      5
    ]
  },
  {
    "id": "demo-final-163472573924932",
    "question": "What planning response would be consistent with StudyHub’s features if a learner discovers they are behind schedule?",
    "answer": "Inference: If progress tracking shows a delay, the learner could refine the study plan because StudyHub supports adjusting plans as learning progresses.",
    "pages": [
      6,
      9
    ]
  },
  {
    "id": "demo-final-92182871608338",
    "question": "Why could StudyHub still flag a weak area after a learner has completed all relevant lecture materials?",
    "answer": "Inference: If Anki statistics indicate difficulty, a weak area could still be flagged because StudyHub considers those statistics alongside material coverage.",
    "pages": [
      9
    ]
  },
  {
    "id": "demo-final-70938988137248",
    "question": "Which StudyHub planning features could help a learner who wants to preserve planned days off?",
    "answer": "Inference: If days off are part of the learner’s preferences, customizable scheduling and the days-off overview could help build a plan around them.",
    "pages": [
      6,
      7
    ]
  }
] as const;


/** Generic preview for other documents; final-slides.pdf uses the imported deck above. */
const DEMO_FLASHCARDS: readonly Flashcard[] = [
  { id: 'demo-card-1', question: 'Demo question 1', answer: 'Demo answer 1', demo: true },
  { id: 'demo-card-2', question: 'Demo question 2', answer: 'Demo answer 2', demo: true },
  { id: 'demo-card-3', question: 'Demo question 3', answer: 'Demo answer 3', demo: true },
  { id: 'demo-card-4', question: 'Demo question 4', answer: 'Demo answer 4', demo: true },
  { id: 'demo-card-5', question: 'Demo question 5', answer: 'Demo answer 5', demo: true },
];

export function demoFlashcards(filename = '', pdfId: string | null = null): Flashcard[] {
  if (filename.trim().toLowerCase() === 'final-slides.pdf') {
    return FINAL_SLIDES_CARDS.map(card => ({
      id: card.id, question: card.question, answer: card.answer, demo: true,
      source: { pdfId, pdfName: filename, pages: [...card.pages], evidence: 'Source-page reference preserved from the supplied Anki package.' },
    }));
  }
  return DEMO_FLASHCARDS.map(card => ({ ...card }));
}

export const DEMO_GENERATION_STAGES = [
  { label: 'Reading slides…', duration: 1200, progress: 15 },
  { label: 'Creating flashcards…', duration: 1400, progress: 50 },
  { label: 'Finishing your deck…', duration: 1000, progress: 85 },
] as const;

function wait(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const onAbort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', onAbort); resolve(); }, milliseconds);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

/** A bounded, cancellable preparation run; the caller persists the resulting deck. */
export async function prepareDemoFlashcards(
  filename: string, pdfId: string,
  onStage: (label: string, progress: number) => void,
  signal: AbortSignal,
  delay: (milliseconds: number, signal: AbortSignal) => Promise<void> = wait,
): Promise<Flashcard[]> {
  for (const stage of DEMO_GENERATION_STAGES) {
    signal.throwIfAborted();
    onStage(stage.label, stage.progress);
    await delay(stage.duration, signal);
  }
  signal.throwIfAborted();
  return demoFlashcards(filename, pdfId);
}
