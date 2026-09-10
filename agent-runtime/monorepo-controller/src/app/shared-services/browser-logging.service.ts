import { Injectable } from '@angular/core';
import { BACKEND_URL } from './backend-url';

type BrowserLogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
type ConsoleMethod = 'debug' | 'log' | 'info' | 'warn' | 'error';
type XhrRequest = { method: string; url: string; startedAt: number };

const LOG_ENDPOINT = `${BACKEND_URL}/api/sys-logs/browser`;
const MAX_MESSAGE_LENGTH = 12000;

@Injectable({ providedIn: 'root' })
export class BrowserLoggingService {
  private installed = false;
  private originalFetch: typeof fetch | null = null;
  private readonly originalConsole: Record<ConsoleMethod, (...data: unknown[]) => void> = {
    debug: console.debug.bind(console),
    log: console.log.bind(console),
    info: console.info.bind(console),
    warn: console.warn.bind(console),
    error: console.error.bind(console),
  };

  install(): void {
    if (this.installed) return;
    this.installed = true;
    this.originalFetch = globalThis.fetch.bind(globalThis);
    this.patchConsole();
    this.captureWindowErrors();
    this.patchFetch();
    this.patchXmlHttpRequest();
    this.info('monorepo-controller/src/app/shared-services/browser-logging.service.ts', 'Browser runtime logging installed.');
  }

  debug(source: string, message: string, details?: unknown): void {
    this.send('DEBUG', source, message, details);
  }

  info(source: string, message: string, details?: unknown): void {
    this.send('INFO', source, message, details);
  }

  warn(source: string, message: string, details?: unknown): void {
    this.send('WARN', source, message, details);
  }

  error(source: string, message: string, details?: unknown): void {
    this.send('ERROR', source, message, details);
  }

  captureError(source: string, message: string, error: unknown): void {
    this.error(source, message, this.describeError(error));
  }

  describeError(error: unknown): Record<string, unknown> | string {
    if (error instanceof Error) return { name: error.name, message: error.message, stack: error.stack };
    return this.serializeValue(error);
  }

  private patchConsole(): void {
    const levelByMethod: Record<ConsoleMethod, BrowserLogLevel> = {
      debug: 'DEBUG',
      log: 'INFO',
      info: 'INFO',
      warn: 'WARN',
      error: 'ERROR',
    };

    for (const method of Object.keys(levelByMethod) as ConsoleMethod[]) {
      console[method] = (...args: unknown[]) => {
        this.originalConsole[method](...args);
        this.send(levelByMethod[method], 'monorepo-controller/src/app/browser-console', this.serializeConsoleArguments(args));
      };
    }
  }

  private captureWindowErrors(): void {
    window.addEventListener('error', (event) => {
      this.error('monorepo-controller/src/app/browser-runtime', event.message || 'Browser runtime error.', {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        error: this.describeError(event.error),
      });
    });
    window.addEventListener('unhandledrejection', (event) => {
      this.error('monorepo-controller/src/app/browser-runtime', 'Unhandled browser promise rejection.', {
        reason: this.describeError(event.reason),
      });
    });
  }

  private patchFetch(): void {
    const originalFetch = this.originalFetch;
    if (!originalFetch) return;

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const startedAt = performance.now();
      const method = init?.method ?? (input instanceof Request ? input.method : 'GET');
      const url = this.requestUrl(input);
      try {
        const response = await originalFetch(input, init);
        if (!response.ok && !this.isLogEndpoint(url)) {
          this.error('monorepo-controller/src/app/browser-network', `Fetch failed with HTTP ${response.status}.`, {
            method,
            url,
            status: response.status,
            durationMs: this.duration(startedAt),
          });
        }
        return response;
      } catch (error) {
        if (!this.isLogEndpoint(url)) {
          this.error('monorepo-controller/src/app/browser-network', 'Fetch request failed.', {
            method,
            url,
            durationMs: this.duration(startedAt),
            error: this.describeError(error),
          });
        }
        throw error;
      }
    };
  }

  private patchXmlHttpRequest(): void {
    const requests = new WeakMap<XMLHttpRequest, XhrRequest>();
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    const service = this;

    XMLHttpRequest.prototype.open = function open(method: string, url: string | URL, async = true, username?: string | null, password?: string | null): void {
      const requestAsync = async !== false;
      requests.set(this, { method, url: service.absoluteUrl(url), startedAt: performance.now() });
      originalOpen.call(this, method, url, requestAsync, username ?? undefined, password ?? undefined);
    };

    XMLHttpRequest.prototype.send = function send(body?: Document | XMLHttpRequestBodyInit | null): void {
      const report = (message: string, includeStatus: boolean): void => {
        const request = requests.get(this);
        if (!request || service.isLogEndpoint(request.url)) return;
        service.error('monorepo-controller/src/app/browser-xhr', message, {
          method: request.method,
          url: request.url,
          status: includeStatus ? this.status : undefined,
          statusText: includeStatus ? this.statusText : undefined,
          durationMs: service.duration(request.startedAt),
        });
      };

      this.addEventListener('loadend', () => {
        if (this.status >= 400) report(`XHR failed with HTTP ${this.status}.`, true);
      }, { once: true });
      this.addEventListener('error', () => report('XHR network error.', false), { once: true });
      this.addEventListener('timeout', () => report('XHR timed out.', false), { once: true });
      this.addEventListener('abort', () => report('XHR aborted.', false), { once: true });
      originalSend.call(this, body ?? null);
    };
  }

  private send(level: BrowserLogLevel, source: string, message: string, details?: unknown): void {
    const body = JSON.stringify({
      level,
      source,
      message: this.limit(message || 'Browser application log.'),
      details,
      timestamp: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
    });

    const blob = new Blob([body], { type: 'application/json' });
    if (navigator.sendBeacon(LOG_ENDPOINT, blob)) return;

    const fetchLog = this.originalFetch ?? globalThis.fetch.bind(globalThis);
    void fetchLog(LOG_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    }).catch(() => undefined);
  }

  private requestUrl(input: RequestInfo | URL): string {
    if (typeof input === 'string') return this.absoluteUrl(input);
    if (input instanceof URL) return input.toString();
    return this.absoluteUrl(input.url);
  }

  private absoluteUrl(url: string | URL): string {
    try {
      return new URL(String(url), window.location.href).toString();
    } catch {
      return String(url);
    }
  }

  private isLogEndpoint(url: string): boolean {
    return this.absoluteUrl(url).startsWith(LOG_ENDPOINT);
  }

  private duration(startedAt: number): number {
    return Math.round(performance.now() - startedAt);
  }

  private serializeConsoleArguments(args: unknown[]): string {
    return this.limit(args.map((arg) => this.serializeValue(arg)).join(' '));
  }

  private serializeValue(value: unknown): string {
    if (typeof value === 'string') return value;
    if (value instanceof Error) return value.stack ?? `${value.name}: ${value.message}`;
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  private limit(value: string): string {
    return value.length > MAX_MESSAGE_LENGTH ? `${value.slice(0, MAX_MESSAGE_LENGTH)}...` : value;
  }
}
