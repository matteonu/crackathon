import { Component, inject, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { ZardAlertComponent } from '@/shared/components/alert';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardImports } from '@/shared/components/card';
import { ZardInputComponent } from '@/shared/components/input';
import { ZardSelectImports } from '@/shared/components/select';
import { ZardTextareaComponent } from '@/shared/components/textarea';

interface Card {
  front: string;
  back: string;
  type: string;
  source_pages: number[];
}

type Step = 1 | 2 | 3;

const MAX_PDF_BYTES = 50 * 1024 * 1024;

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

@Component({
  selector: 'app-flashcards',
  imports: [
    FormsModule,
    ZardAlertComponent,
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardImports,
    ZardInputComponent,
    ZardSelectImports,
    ZardTextareaComponent,
  ],
  templateUrl: './flashcards.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class FlashcardsComponent {
  private http = inject(HttpClient);

  readonly steps = ['Upload slides', 'Review examples', 'Download deck'];
  readonly feedbackOptions = ['More detail', 'Shorter', 'More challenging', 'Just right'];

  step: Step = 1;
  loading = false;
  error = '';
  dragging = false;

  file: File | null = null;
  // Started as soon as a file is chosen; the click awaits it. Reading early matters:
  // Chrome refuses to read a file that changed on disk after it was picked.
  private pdfBase64: Promise<string> | null = null;
  mode: 'quick' | 'deep' = 'quick';

  examples: Card[] = [];
  feedback: (string | null)[] = [];
  generalFeedback = '';

  deckName = 'Lecture deck';
  cardCount = '50';
  deck: { blob: Blob; count: number } | null = null;

  useFile(file: File | undefined | null) {
    this.error = '';
    if (!file) return;
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      this.error = 'Please choose a PDF file.';
      return;
    }
    if (file.size > MAX_PDF_BYTES) {
      this.error = 'This PDF is larger than 50 MB.';
      return;
    }
    this.file = file;
    this.pdfBase64 = readAsBase64(file);
    this.pdfBase64.catch(() => {}); // reported when the user clicks
  }

  onFileInput(event: Event) {
    this.useFile((event.target as HTMLInputElement).files?.[0]);
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragging = false;
    this.useFile(event.dataTransfer?.files[0]);
  }

  removeFile() {
    this.file = null;
    this.pdfBase64 = null;
  }

  fileSize(): string {
    return this.file ? `${(this.file.size / 1024 / 1024).toFixed(2)} MB` : '';
  }

  async makeExamples() {
    if (!this.file || !this.pdfBase64) return;
    this.start();
    let pdfBase64: string;
    try {
      pdfBase64 = await this.pdfBase64;
    } catch (err) {
      this.loading = false;
      const reason = err instanceof DOMException ? ` (${err.name})` : '';
      this.error =
        `Your browser could not read this file${reason}. ` +
        'If it was still downloading, syncing (iCloud, OneDrive) or changed after you chose it, choose it again.';
      this.removeFile();
      return;
    }
    this.http
      .post<{ cards: Card[] }>('/api/flashcards/examples', {
        filename: this.file.name,
        pdfBase64,
        mode: this.mode,
      })
      .subscribe({
        next: (res) => {
          this.loading = false;
          if (!res.cards.length) {
            this.error = 'The model returned no example cards. Try again or use Deep mode.';
            return;
          }
          this.examples = res.cards;
          this.feedback = res.cards.map(() => null);
          this.step = 2;
        },
        error: (err) => this.fail(err, 'The example cards could not be generated.'),
      });
  }

  toggleFeedback(index: number, option: string) {
    this.feedback[index] = this.feedback[index] === option ? null : option;
  }

  async generateDeck() {
    if (!this.file || !this.pdfBase64) return;
    this.start();
    this.deck = null;
    const pdfBase64 = await this.pdfBase64; // already read successfully in step 1
    const perCard = this.examples
      .map((card, i) => (this.feedback[i] ? { card: card.front, feedback: this.feedback[i] } : null))
      .filter((item) => item !== null);
    this.http
      .post<{ cards: Card[] }>('/api/flashcards/final', {
        filename: this.file.name,
        pdfBase64,
        mode: this.mode,
        feedback: perCard,
        generalFeedback: this.generalFeedback,
        cardCount: Number(this.cardCount),
      })
      .subscribe({
        next: (res) => {
          if (!res.cards.length) {
            this.loading = false;
            this.error = 'The model returned no cards.';
            return;
          }
          this.http
            .post('/api/flashcards/export', { deckName: this.deckName, cards: res.cards }, { responseType: 'blob' })
            .subscribe({
              next: (blob) => {
                this.loading = false;
                this.deck = { blob, count: res.cards.length };
              },
              error: (err) => this.fail(err, 'The deck was generated but could not be exported.'),
            });
        },
        error: (err) => this.fail(err, 'The deck could not be generated.'),
      });
  }

  download() {
    if (!this.deck) return;
    const url = URL.createObjectURL(this.deck.blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${this.deckName.replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'deck'}.apkg`;
    link.click();
    URL.revokeObjectURL(url);
  }

  restart() {
    this.step = 1;
    this.error = '';
    this.examples = [];
    this.feedback = [];
    this.generalFeedback = '';
    this.deck = null;
  }

  private start() {
    this.loading = true;
    this.error = '';
  }

  private fail(err: HttpErrorResponse, fallback: string) {
    this.loading = false;
    this.error = (err.error && typeof err.error === 'object' && 'error' in err.error ? err.error.error : null) ?? fallback;
  }
}
