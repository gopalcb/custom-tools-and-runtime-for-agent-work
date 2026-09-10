import { Body, Controller, HttpCode, Post } from '@nestjs/common';
import { ApplicationLogService } from './application-log.service';

@Controller('api/sys-logs')
export class ApplicationLogsController {
  constructor(private readonly applicationLogs: ApplicationLogService) {}

  @Post('browser')
  @HttpCode(202)
  async browserLog(@Body() payload: unknown): Promise<{ status: string }> {
    await this.applicationLogs.writeLog(payload, 'monorepo-controller/src/app/browser-runtime');
    return { status: 'accepted' };
  }
}
