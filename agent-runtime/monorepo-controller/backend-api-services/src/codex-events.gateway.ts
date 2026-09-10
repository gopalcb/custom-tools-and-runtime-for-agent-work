import { Logger } from '@nestjs/common';
import { ConnectedSocket, MessageBody, OnGatewayConnection, SubscribeMessage, WebSocketGateway, WebSocketServer } from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { ApplicationLogService } from './application-log.service';
import { CodexApiClientService } from './codex-api-client.service';
import { CodexSocketEvent, StartTurnRequest, TurnReference, TurnSnapshot } from './contracts';

const MAX_BUFFERED_EVENTS = 500;
const SOURCE = 'monorepo-controller/backend-api-services/src/codex-events.gateway.ts';

interface ActiveTurn {
  events: Record<string, unknown>[];
  complete: boolean;
}

@WebSocketGateway({ namespace: '/codex', cors: { origin: process.env.UI_ORIGIN?.split(',') ?? true } })
export class CodexEventsGateway implements OnGatewayConnection {
  @WebSocketServer()
  server!: Server;

  private readonly logger = new Logger(CodexEventsGateway.name);
  private readonly turns = new Map<string, ActiveTurn>();
  private readonly streams = new Set<string>();

  constructor(
    private readonly codexApi: CodexApiClientService,
    private readonly applicationLogs: ApplicationLogService,
  ) {}

  handleConnection(client: Socket): void {
    void this.applicationLogs.writeBackendLog('DEBUG', `Codex socket connected: ${client.id}.`, SOURCE);
    client.emit('codex.ready', { transport: 'socket.io' });
  }

  @SubscribeMessage('codex.subscribe')
  subscribe(@ConnectedSocket() client: Socket, @MessageBody() payload: { turnId?: string }): TurnSnapshot | { error: string } {
    const turnId = payload?.turnId;
    if (!turnId || !this.turns.has(turnId)) {
      void this.applicationLogs.writeBackendLog('WARN', `Socket ${client.id} attempted to subscribe to an unknown Codex turn.`, SOURCE, { turnId });
      return { error: 'Unknown turn id' };
    }
    void this.applicationLogs.writeBackendLog('DEBUG', `Socket ${client.id} subscribed to Codex turn ${turnId}.`, SOURCE);
    void client.join(this.room(turnId));
    return this.snapshot(turnId);
  }

  async startTurn(payload: StartTurnRequest): Promise<TurnReference> {
    const reference = await this.codexApi.startTurn(payload);
    void this.applicationLogs.writeBackendLog('INFO', `Codex turn ${reference.turn_id} started.`, SOURCE, { threadId: reference.thread_id });
    this.turns.set(reference.turn_id, { events: [], complete: false });
    void this.watchTurn(reference.turn_id);
    return reference;
  }

  snapshot(turnId: string): TurnSnapshot {
    const turn = this.turns.get(turnId);
    if (!turn) return { turnId, events: [], complete: true };
    return { turnId, events: [...turn.events], complete: turn.complete };
  }

  private async watchTurn(turnId: string): Promise<void> {
    if (this.streams.has(turnId)) return;
    this.streams.add(turnId);
    void this.applicationLogs.writeBackendLog('DEBUG', `Watching Codex event stream for ${turnId}.`, SOURCE);
    try {
      for await (const event of this.codexApi.streamTurn(turnId)) {
        const turn = this.turns.get(turnId);
        if (!turn) break;
        turn.events.push(event);
        if (turn.events.length > MAX_BUFFERED_EVENTS) turn.events.shift();
        this.server.to(this.room(turnId)).emit('codex.event', { turnId, event } satisfies CodexSocketEvent);
      }
      this.completeTurn(turnId);
    } catch (error) {
      this.logger.error(`Unable to stream Codex turn ${turnId}: ${this.errorMessage(error)}`);
      void this.applicationLogs.writeBackendLog('ERROR', `Unable to stream Codex turn ${turnId}.`, SOURCE, { error: this.errorMessage(error) });
      const event = { type: 'codex.stream.error', message: this.errorMessage(error) };
      const turn = this.turns.get(turnId);
      if (turn) turn.events.push(event);
      this.server.to(this.room(turnId)).emit('codex.event', { turnId, event } satisfies CodexSocketEvent);
      this.completeTurn(turnId);
    } finally {
      this.streams.delete(turnId);
    }
  }

  private completeTurn(turnId: string): void {
    const turn = this.turns.get(turnId);
    if (turn) turn.complete = true;
    void this.applicationLogs.writeBackendLog('INFO', `Codex turn ${turnId} completed.`, SOURCE);
    this.server.to(this.room(turnId)).emit('codex.completed', { turnId });
  }

  private room(turnId: string): string {
    return `turn:${turnId}`;
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }
}
