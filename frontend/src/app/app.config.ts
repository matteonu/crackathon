import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { provideZard } from '@/shared/core/provider/providezard';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideHttpClient(withXhr()),
    provideRouter(routes),
    provideZard(),
  ],
};
