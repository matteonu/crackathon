import { Routes } from '@angular/router';

import { DashboardComponent } from './dashboard/dashboard.component';

export const routes: Routes = [
  { path: '', component: DashboardComponent, title: 'Dashboard · crackathon' },
  {
    path: 'flashcards',
    // Lazy: keeps the PDF/flashcard code out of the initial bundle.
    loadComponent: () => import('./flashcards/flashcards.component').then((m) => m.FlashcardsComponent),
    title: 'Flashcards · crackathon',
  },
  { path: '**', redirectTo: '' },
];
