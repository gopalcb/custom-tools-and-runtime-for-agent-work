import { Module } from '@nestjs/common';
import { ApplicationLogService } from './application-log.service';
import { ApplicationLogsController } from './application-logs.controller';
import { CodexApiClientService } from './codex-api-client.service';
import { CodexController } from './codex.controller';
import { CodexEventsGateway } from './codex-events.gateway';

@Module({
  controllers: [CodexController, ApplicationLogsController],
  providers: [ApplicationLogService, CodexApiClientService, CodexEventsGateway],
})
export class AppModule {}
