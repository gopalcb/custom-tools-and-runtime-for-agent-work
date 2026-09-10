import { ErrorHandler, Injectable } from '@angular/core';
import { BrowserLoggingService } from './browser-logging.service';

@Injectable()
export class BrowserErrorHandler implements ErrorHandler {
  constructor(private readonly browserLogs: BrowserLoggingService) {}

  handleError(error: unknown): void {
    this.browserLogs.captureError('monorepo-controller/src/app/shared-services/browser-error-handler.ts', 'Angular runtime error.', error);
  }
}
