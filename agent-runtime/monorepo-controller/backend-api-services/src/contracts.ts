/** Shared HTTP and Socket.IO payloads for live Codex turns. */

export interface StartTurnRequest {
  prompt: string;
  thread_id?: string;
  sandbox?: 'read_only' | 'workspace_write' | 'full_access';
  model?: string;
  ephemeral?: boolean;
}

export interface TurnReference {
  thread_id: string;
  turn_id: string;
}

export interface CodexSocketEvent {
  turnId: string;
  event: Record<string, unknown>;
}

export interface TurnSnapshot {
  turnId: string;
  events: Record<string, unknown>[];
  complete: boolean;
}

export type ApplicationLogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

export interface RuntimeLogRequest {
  level?: string;
  source?: string;
  message?: string;
  details?: unknown;
  timestamp?: string;
  url?: string;
  userAgent?: string;
}
