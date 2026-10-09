import { Component, inject, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-root',
  imports: [],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit {
  private http = inject(HttpClient);
  message = 'Loading...';

  ngOnInit() {
    this.http.get<{ message: string }>('/api/hello').subscribe({
      next: (res) => (this.message = res.message),
      error: () => (this.message = 'Could not reach the backend'),
    });
  }
}
