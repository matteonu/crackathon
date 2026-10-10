import { bootstrapApplication } from '@angular/platform-browser';
import { provideBrowserGlobalErrorListeners, provideZonelessChangeDetection } from '@angular/core';
import { provideRouter, withHashLocation, withViewTransitions } from '@angular/router';
import { AppComponent } from './app/app.component';
import { routes } from './app/app.routes';

bootstrapApplication(AppComponent, {
  providers:[
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes,withHashLocation(),withViewTransitions({
      skipInitialTransition:true,
      onViewTransitionCreated:({transition})=>{
        if(matchMedia('(prefers-reduced-motion: reduce)').matches)transition.skipTransition();
      }
    }))
  ]
}).catch(error=>console.error(error));
