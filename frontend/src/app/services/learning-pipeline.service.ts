import { Injectable } from '@angular/core';
import type { Material, LearningMode, LearningTask } from '../models/material';
import { parseStudyResult, StudyResult } from '../models/learning';

@Injectable({ providedIn: 'root' })
export class LearningPipelineService {
  resultUrl(id: string, mode: LearningMode = 'shallow', task: LearningTask = 'flashcards'): string { return `/api/learning/documents/${encodeURIComponent(id)}/result.json?mode=${mode}&task=${task}`; }

  async remove(id: string): Promise<void> {
    await this.request(`/api/learning/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
  }

  private async request(url: string, init?: RequestInit): Promise<unknown> {
    let response: Response;
    try {
      response = await fetch(url, { ...init, cache: 'no-store', signal: AbortSignal.timeout(30000) });
    } catch {
      throw new Error('Cannot reach the server. Check your connection and retry processing.');
    }
    let data: unknown;
    try { data = await response.json(); }
    catch { throw new Error('The learning API is unavailable. Reload the page and retry processing.'); }
    if (!response.ok) {
      throw new Error(typeof (data as {error?:unknown})?.error === 'string'
        ? (data as {error:string}).error : 'The server could not process this file. Retry processing.');
    }
    return data;
  }

  async process(file: Material, receive: (result: StudyResult) => Promise<void>, resume = false, mode: LearningMode = 'shallow', task: LearningTask = 'flashcards', count = 60): Promise<void> {
    const submit = () => this.request(`/api/learning/documents/${encodeURIComponent(file.id)}`, { method: 'POST', headers: { 'X-Filename': encodeURIComponent(file.name), 'X-Learning-Mode': mode, 'X-Learning-Task': task, 'X-Flashcard-Count': String(count) } });
    let data: unknown;
    try { data = resume ? await this.request(this.resultUrl(file.id,mode,task)) : await submit(); }
    catch (error) {
      // An upload can finish just before a page refresh, before the queued job was submitted.
      if (resume && file.processing?.status === 'queued') data = await submit();
      else throw error;
    }
    let previous = '';
    const deadline = Date.now() + 30 * 60 * 1000;
    while (true) {
      const result = parseStudyResult(data, file.id, mode, task);
      const serialized = JSON.stringify(result);
      if (serialized !== previous) { await receive(result); previous = serialized; }
      if (result.status === 'error' || result.status === 'complete') return;
      if (Date.now() >= deadline) throw new Error('Processing is taking longer than expected. Retry to reconnect to saved progress.');
      await new Promise(resolve => setTimeout(resolve, 1500));
      data = await this.request(this.resultUrl(file.id,mode,task));
    }
  }
}
