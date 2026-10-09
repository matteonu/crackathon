import { Component, inject, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ZardButtonComponent } from '@/shared/components/button';

import { LoginComponent } from './login/login.component';

@Component({
  selector: 'app-root',
  imports: [LoginComponent, RouterLink, RouterLinkActive, RouterOutlet, ZardButtonComponent],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class AppComponent implements OnInit {
  private http = inject(HttpClient);
  user: string | null = null;
  checked = false;

  readonly nav = [
    { path: '/', label: 'Dashboard' },
    { path: '/flashcards', label: 'Flashcards' },
  ];

  ngOnInit() {
    // Restore an existing session before deciding which page to show.
    this.http.get<{ username: string }>('/api/me').subscribe({
      next: (res) => {
        this.user = res.username;
        this.checked = true;
      },
      error: () => (this.checked = true),
    });
  }

  logout() {
    this.http.post('/api/logout', {}).subscribe(() => (this.user = null));
  }
}
