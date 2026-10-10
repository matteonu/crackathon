import { Injectable } from '@angular/core';
import type { Material, LearningMode } from '../models/material';
import { parseStudyResult, StudyResult } from '../models/learning';

@Injectable({ providedIn: 'root' })
export class LearningPipelineService {
  resultUrl(id: string, mode: LearningMode = 'shallow'): string { return `/api/learning/documents/${encodeURIComponent(id)}/result.json?mode=${mode}`; }

  private async request(url: string, init?: RequestInit): Promise<unknown> {
    let response: Response;
    try {
      response = await fetch(url, { ...init, cache: 'no-store', signal: AbortSignal.timeout(30000) });
    } catch {
      throw new Error('Cannot reach the Python server. Start it and retry processing.');
    }
    let data: unknown;
    try { data = await response.json(); }
    catch { throw new Error('The learning API is unavailable. Start the Python server and use the integrated learning view.'); }
    if (!response.ok) {
      throw new Error(typeof (data as {error?:unknown})?.error === 'string'
        ? (data as {error:string}).error : 'The Python server could not process this file. Retry processing.');
    }
    return data;
  }

  async process(file: Material, receive: (result: StudyResult) => Promise<void>, resume = false, mode: LearningMode = 'shallow'): Promise<void> {
    let data = await this.request(resume ? this.resultUrl(file.id,mode) : `/api/learning/documents/${encodeURIComponent(file.id)}`,
      resume ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/pdf', 'X-Filename': encodeURIComponent(file.name), 'X-Learning-Mode': mode }, body: file.blob });
    let previous = '';
    const deadline = Date.now() + 30 * 60 * 1000;
    while (true) {
      const result = parseStudyResult(data, file.id, mode);
      const serialized = JSON.stringify(result);
      if (serialized !== previous) { await receive(result); previous = serialized; }
      if (result.status === 'error' || result.status === 'complete') return;
      if (Date.now() >= deadline) throw new Error('Processing is taking longer than expected. Retry to reconnect to saved progress.');
      await new Promise(resolve => setTimeout(resolve, 1500));
      data = await this.request(this.resultUrl(file.id,mode));
    }
  }
}
