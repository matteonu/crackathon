import test from 'node:test';
import assert from 'node:assert/strict';
import { demoFlashcards, DEMO_GENERATION_STAGES, prepareDemoFlashcards } from '../src/app/models/demo-flashcards.ts';

test('demo runs return the same cards and stable IDs after a preview is edited', () => {
  const first = demoFlashcards();
  const expected = structuredClone(first);
  first[0].answer = 'Changed during a preview';
  assert.deepEqual(demoFlashcards(), expected);
  assert.equal(new Set(expected.map(card => card.id)).size, expected.length);
  assert.ok(expected.every(card => card.demo && card.question && card.answer));
});

test('final-slides.pdf returns all 15 imported Anki cards in order with current PDF links', () => {
  const cards = demoFlashcards('final-slides.pdf', 'uploaded-pdf');
  assert.equal(cards.length, 15);
  assert.equal(cards[0].question, 'What broad learning needs does StudyHub’s Moodle with Benefits pillar address?');
  assert.equal(cards[0].answer, 'It addresses organizing course materials, understanding lecture content, and reviewing what has been learned.');
  assert.deepEqual(cards[0].source?.pages, [4]);
  assert.deepEqual(cards[1].source?.pages, [6, 7]);
  assert.ok(cards.every(card => card.source?.pdfId === 'uploaded-pdf' && card.source.pdfName === 'final-slides.pdf'));
  assert.equal(new Set(cards.map(card => card.id)).size, 15);
  assert.deepEqual(demoFlashcards('FINAL-SLIDES.PDF', 'uploaded-pdf').map(card => card.question), cards.map(card => card.question));
  assert.equal(demoFlashcards('another-file.pdf').length, 5);
  cards[0].source!.pages.push(99);
  assert.deepEqual(demoFlashcards('final-slides.pdf')[0].source?.pages, [4]);
  assert.ok(cards.every(card => !card.question.includes('<') && !card.question.includes('localhost') && !card.question.includes('\ufffd')));
});

test('demo progresses through a bounded loading sequence before returning the deck', async () => {
  const phases: string[] = [], delays: number[] = [];
  const cards = await prepareDemoFlashcards('final-slides.pdf', 'pdf',
    label => phases.push(label), new AbortController().signal,
    async milliseconds => { delays.push(milliseconds); });
  assert.deepEqual(phases, DEMO_GENERATION_STAGES.map(stage => stage.label));
  assert.equal(delays.reduce((sum, value) => sum + value, 0), 3600);
  assert.equal(cards.length, 15);
});

test('switching document or disabling demo cancels pending results', async () => {
  const request = new AbortController();
  let phases = 0;
  await assert.rejects(prepareDemoFlashcards('final-slides.pdf', 'old-pdf',
    () => phases++, request.signal, async () => { request.abort(); }), { name: 'AbortError' });
  assert.equal(phases, 1);
  const cancelled = new AbortController();
  cancelled.abort();
  await assert.rejects(prepareDemoFlashcards('final-slides.pdf', 'pdf', () => assert.fail('Started after cancel'), cancelled.signal), { name: 'AbortError' });
  const pendingRequest = new AbortController();
  const pending = prepareDemoFlashcards('final-slides.pdf', 'pdf', () => {}, pendingRequest.signal);
  pendingRequest.abort();
  await assert.rejects(pending, { name: 'AbortError' });
});
