import { Component, inject, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient } from '@angular/common/http';

import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardCardImports } from '@/shared/components/card';
import { ZardTableImports } from '@/shared/components/table';

interface Resource {
  kind: 'resource' | 'doc';
  title: string;
  url: string | null;
}

interface Course {
  id: number;
  code: string;
  title: string;
  term: 'HS' | 'FS' | null;
  ects: number;
  professor: string | null;
  desired_grade: number | null;
  resources: Resource[];
}

interface Semester {
  id: number;
  label: string;
  study_hours_per_week: number | null;
  courses: Course[];
}

interface Dashboard {
  user: { username: string; birth_date: string | null; study_start: string | null };
  semesters: Semester[];
}

@Component({
  selector: 'app-dashboard',
  imports: [ZardBadgeComponent, ZardCardImports, ZardTableImports],
  templateUrl: './dashboard.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class DashboardComponent implements OnInit {
  private http = inject(HttpClient);
  data: Dashboard | null = null;
  error = '';

  ngOnInit() {
    this.http.get<Dashboard>('/api/dashboard').subscribe({
      next: (res) => (this.data = res),
      error: () => (this.error = 'Could not load your data.'),
    });
  }

  get currentSemester(): Semester | null {
    return this.data?.semesters.at(-1) ?? null;
  }

  get totalEcts(): number {
    return this.data?.semesters.reduce((sum, s) => sum + this.semesterEcts(s), 0) ?? 0;
  }

  semesterEcts(semester: Semester): number {
    return semester.courses.reduce((sum, c) => sum + c.ects, 0);
  }

  age(birthDate: string | null): number | null {
    if (!birthDate) return null;
    const born = new Date(birthDate);
    const now = new Date();
    const hadBirthday =
      now.getMonth() > born.getMonth() || (now.getMonth() === born.getMonth() && now.getDate() >= born.getDate());
    return now.getFullYear() - born.getFullYear() - (hadBirthday ? 0 : 1);
  }
}
