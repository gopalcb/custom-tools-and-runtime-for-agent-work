import { Module } from '@nestjs/common';
import { ApplicationLogService } from './application-log.service';
import { ApplicationLogsController } from './application-logs.controller';
import { ControllerController } from './controller.controller';
import { MonorepoDataService } from './monorepo-data.service';
import { TaskRunnerService } from './task-runner.service';

@Module({
  controllers: [ControllerController, ApplicationLogsController],
  providers: [ApplicationLogService, MonorepoDataService, TaskRunnerService],
})
export class AppModule {}
