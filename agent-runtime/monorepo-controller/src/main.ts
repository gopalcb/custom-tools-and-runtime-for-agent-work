import { bootstrapApplication } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { ENVIRONMENT_INITIALIZER, ErrorHandler, inject, provideZonelessChangeDetection } from '@angular/core';
import { AppComponent } from './app/app.component';
import { routes } from './app/app.routes';
import { BrowserErrorHandler } from './app/shared-services/browser-error-handler';
import { BrowserLoggingService } from './app/shared-services/browser-logging.service';

bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(routes),
    provideHttpClient(),
    provideZonelessChangeDetection(),
    { provide: ErrorHandler, useClass: BrowserErrorHandler },
    { provide: ENVIRONMENT_INITIALIZER, multi: true, useValue: () => inject(BrowserLoggingService).install() },
  ],
})
  .catch((error: unknown) => console.error(error));
