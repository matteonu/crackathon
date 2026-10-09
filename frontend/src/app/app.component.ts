import { Component, inject, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit {
  private http = inject(HttpClient);
  user: string | null = null;
  username = '';
  password = '';
  error = '';
  message = '';

  ngOnInit() {
    this.http.get<{ username: string }>('/api/me').subscribe({
      next: (res) => this.onLoggedIn(res.username),
      error: () => (this.user = null),
    });
  }

  login() {
    this.error = '';
    this.http
      .post<{ username: string }>('/api/login', { username: this.username, password: this.password })
      .subscribe({
        next: (res) => this.onLoggedIn(res.username),
        error: () => (this.error = 'Invalid username or password'),
      });
  }

  logout() {
    this.http.post('/api/logout', {}).subscribe(() => {
      this.user = null;
      this.message = '';
    });
  }

  private onLoggedIn(username: string) {
    this.user = username;
    this.password = '';
    this.http.get<{ message: string }>('/api/hello').subscribe({
      next: (res) => (this.message = res.message),
      error: () => (this.message = 'Could not reach the backend'),
    });
  }
}
