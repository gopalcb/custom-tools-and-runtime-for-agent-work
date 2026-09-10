import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { ApplicationLogService } from './application-log.service';
import { CodexApiClientService } from './codex-api-client.service';
import { CodexEventsGateway } from './codex-events.gateway';
import { StartTurnRequest, TurnReference } from './contracts';

const SOURCE = 'monorepo-controller/backend-api-services/src/codex.controller.ts';

@Controller('api/codex')
export class CodexController {
  constructor(
    private readonly codexApi: CodexApiClientService,
    private readonly events: CodexEventsGateway,
    private readonly applicationLogs: ApplicationLogService,
  ) {}

  @Get('health')
  health(): Promise<Record<string, unknown>> {
    void this.applicationLogs.writeBackendLog('DEBUG', 'Codex health check requested.', SOURCE);
    return this.codexApi.health();
  }

  @Post('turns')
  startTurn(@Body() payload: StartTurnRequest): Promise<TurnReference> {
    void this.applicationLogs.writeBackendLog('INFO', 'Codex turn start requested.', SOURCE, {
      hasThreadId: Boolean(payload.thread_id),
      sandbox: payload.sandbox,
    });
    return this.events.startTurn(payload);
  }

  @Get('turns/:turnId')
  turnSnapshot(@Param('turnId') turnId: string) {
    return this.events.snapshot(turnId);
  }

  @Post('turns/:turnId/steer')
  steerTurn(@Param('turnId') turnId: string, @Body() payload: { prompt?: string }): Promise<Record<string, unknown>> {
    void this.applicationLogs.writeBackendLog('INFO', `Codex turn steer requested for ${turnId}.`, SOURCE);
    return this.codexApi.steerTurn(turnId, payload.prompt ?? '');
  }

  @Post('turns/:turnId/interrupt')
  interruptTurn(@Param('turnId') turnId: string): Promise<Record<string, unknown>> {
    void this.applicationLogs.writeBackendLog('INFO', `Codex turn interrupt requested for ${turnId}.`, SOURCE);
    return this.codexApi.interruptTurn(turnId);
  }
}
