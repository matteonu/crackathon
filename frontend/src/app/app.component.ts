import { Component, inject, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient } from '@angular/common/http';

import { DashboardComponent } from './dashboard/dashboard.component';
import { LoginComponent } from './login/login.component';

@Component({
  selector: 'app-root',
  imports: [DashboardComponent, LoginComponent],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class AppComponent implements OnInit {
  private http = inject(HttpClient);
  user: string | null = null;
  checked = false;

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
}
