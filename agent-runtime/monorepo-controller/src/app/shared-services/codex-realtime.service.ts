import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { io, Socket } from 'socket.io-client';
import { BACKEND_URL } from './backend-url';
import { BrowserLoggingService } from './browser-logging.service';
import { CodexSocketEvent, CodexTurnReference, CodexTurnRequest } from './interfaces';

const SOURCE = 'monorepo-controller/src/app/shared-services/codex-realtime.service.ts';

@Injectable({ providedIn: 'root' })
export class CodexRealtimeService {
  readonly connected = signal(false);
  readonly events = signal<CodexSocketEvent[]>([]);
  readonly completedTurnId = signal<string | null>(null);
  private readonly socket: Socket = io(`${BACKEND_URL}/codex`, { autoConnect: true });

  constructor(
    private readonly http: HttpClient,
    private readonly browserLogs: BrowserLoggingService,
  ) {
    this.socket.on('connect', () => {
      this.connected.set(true);
      this.browserLogs.info(SOURCE, 'Codex realtime socket connected.');
    });
    this.socket.on('disconnect', (reason) => {
      this.connected.set(false);
      this.browserLogs.warn(SOURCE, 'Codex realtime socket disconnected.', { reason });
    });
    this.socket.on('codex.event', (event: CodexSocketEvent) => this.events.update((items) => [...items, event]));
    this.socket.on('codex.completed', (event: { turnId?: string }) => {
      this.completedTurnId.set(event.turnId ?? null);
      this.browserLogs.info(SOURCE, 'Codex realtime turn completed.', { turnId: event.turnId });
    });
  }

  startTurn(payload: CodexTurnRequest): Observable<CodexTurnReference> {
    this.browserLogs.info(SOURCE, 'Starting Codex turn through backend API.', { sandbox: payload.sandbox, ephemeral: payload.ephemeral });
    return this.http.post<CodexTurnReference>(`${BACKEND_URL}/api/codex/turns`, payload);
  }

  subscribe(turnId: string): void {
    this.browserLogs.debug(SOURCE, 'Subscribing to Codex realtime turn.', { turnId });
    this.socket.emit('codex.subscribe', { turnId }, (snapshot: { events?: Record<string, unknown>[] }) => {
      for (const event of snapshot.events ?? []) this.events.update((items) => [...items, { turnId, event }]);
    });
  }

  interrupt(turnId: string): Observable<Record<string, unknown>> {
    this.browserLogs.info(SOURCE, 'Requesting Codex turn interrupt.', { turnId });
    return this.http.post<Record<string, unknown>>(`${BACKEND_URL}/api/codex/turns/${encodeURIComponent(turnId)}/interrupt`, {});
  }
}
