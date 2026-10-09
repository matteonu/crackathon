import { Component, inject, output, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

import { ZardAlertComponent } from '@/shared/components/alert';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardImports } from '@/shared/components/card';
import { ZardInputComponent } from '@/shared/components/input';

@Component({
  selector: 'app-login',
  imports: [FormsModule, ZardAlertComponent, ZardButtonComponent, ZardCardImports, ZardInputComponent],
  templateUrl: './login.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class LoginComponent {
  private http = inject(HttpClient);
  readonly loggedIn = output<string>();

  username = '';
  password = '';
  error = '';
  loading = false;

  submit() {
    this.error = '';
    this.loading = true;
    this.http
      .post<{ username: string }>('/api/login', { username: this.username, password: this.password })
      .subscribe({
        next: (res) => {
          this.loading = false;
          this.password = '';
          this.loggedIn.emit(res.username);
        },
        error: () => {
          this.loading = false;
          this.error = 'Invalid username or password';
        },
      });
  }
}
