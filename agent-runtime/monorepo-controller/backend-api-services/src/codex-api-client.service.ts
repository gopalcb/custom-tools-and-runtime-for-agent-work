import { BadGatewayException, Injectable } from '@nestjs/common';
import { ApplicationLogService } from './application-log.service';
import { StartTurnRequest, TurnReference } from './contracts';

const DEFAULT_DEBUGGER_API_URL = 'http://127.0.0.1:8771';
const SOURCE = 'monorepo-controller/backend-api-services/src/codex-api-client.service.ts';

@Injectable()
export class CodexApiClientService {
  private readonly baseUrl = (process.env.UI_DEBUGGER_API_URL ?? DEFAULT_DEBUGGER_API_URL).replace(/\/$/, '');

  constructor(private readonly applicationLogs: ApplicationLogService) {}

  async health(): Promise<Record<string, unknown>> {
    void this.applicationLogs.writeBackendLog('DEBUG', 'Checking debugger API health.', SOURCE, { baseUrl: this.baseUrl });
    return this.request<Record<string, unknown>>('GET', '/health');
  }

  async startTurn(payload: StartTurnRequest): Promise<TurnReference> {
    void this.applicationLogs.writeBackendLog('INFO', 'Forwarding Codex turn start to debugger API.', SOURCE, {
      sandbox: payload.sandbox,
      ephemeral: payload.ephemeral,
    });
    return this.request<TurnReference>('POST', '/v1/turns', payload);
  }

  async steerTurn(turnId: string, prompt: string): Promise<Record<string, unknown>> {
    void this.applicationLogs.writeBackendLog('INFO', `Forwarding Codex turn steer to debugger API for ${turnId}.`, SOURCE, { promptLength: prompt.length });
    return this.request<Record<string, unknown>>('POST', `/v1/turns/${encodeURIComponent(turnId)}/steer`, { prompt });
  }

  async interruptTurn(turnId: string): Promise<Record<string, unknown>> {
    void this.applicationLogs.writeBackendLog('INFO', `Forwarding Codex turn interrupt to debugger API for ${turnId}.`, SOURCE);
    return this.request<Record<string, unknown>>('POST', `/v1/turns/${encodeURIComponent(turnId)}/interrupt`, {});
  }

  async *streamTurn(turnId: string): AsyncGenerator<Record<string, unknown>> {
    void this.applicationLogs.writeBackendLog('DEBUG', `Opening Codex event stream for ${turnId}.`, SOURCE);
    const response = await this.fetch(`/v1/turns/${encodeURIComponent(turnId)}/stream`);
    if (!response.body) {
      void this.applicationLogs.writeBackendLog('ERROR', `Debugger API returned an empty Codex event stream for ${turnId}.`, SOURCE);
      throw new BadGatewayException('Debugger API returned an empty Codex event stream');
    }
    const decoder = new TextDecoder();
    let pending = '';
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split('\n');
      pending = lines.pop() ?? '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed) yield this.parseEvent(trimmed, turnId);
      }
    }
    const finalLine = (pending + decoder.decode()).trim();
    if (finalLine) yield this.parseEvent(finalLine, turnId);
    void this.applicationLogs.writeBackendLog('DEBUG', `Codex event stream closed for ${turnId}.`, SOURCE);
  }

  private async request<TResponse>(method: string, path: string, payload?: object): Promise<TResponse> {
    const response = await this.fetch(path, {
      method,
      headers: payload ? { 'Content-Type': 'application/json' } : undefined,
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const value: unknown = await response.json().catch(() => null);
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      void this.applicationLogs.writeBackendLog('ERROR', `Debugger API returned invalid JSON for ${method} ${path}.`, SOURCE);
      throw new BadGatewayException('Debugger API returned an invalid JSON object');
    }
    return value as TResponse;
  }

  private async fetch(path: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, init);
    } catch (error) {
      void this.applicationLogs.writeBackendLog('ERROR', `Debugger API unavailable for ${path}.`, SOURCE, { error: this.errorMessage(error) });
      throw new BadGatewayException(`Debugger API is unavailable: ${this.errorMessage(error)}`);
    }
    if (!response.ok) {
      const body = await response.text();
      void this.applicationLogs.writeBackendLog('ERROR', `Debugger API returned HTTP ${response.status} for ${path}.`, SOURCE, { body });
      throw new BadGatewayException(body || `Debugger API returned HTTP ${response.status}`);
    }
    return response;
  }

  private parseEvent(line: string, turnId: string): Record<string, unknown> {
    try {
      const value: unknown = JSON.parse(line);
      if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
    } catch {
      void this.applicationLogs.writeBackendLog('ERROR', `Unable to parse Codex stream event for ${turnId}.`, SOURCE, { raw: line });
    }
    return { type: 'codex.stream.decode_error', turn_id: turnId, raw: line };
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }
}
