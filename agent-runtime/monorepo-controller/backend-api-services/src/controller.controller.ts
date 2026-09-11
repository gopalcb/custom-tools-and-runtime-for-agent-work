import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { ApplicationLogService } from './application-log.service';
import {
  AgentSummary,
  ControllerSnapshot,
  CreateSkillRequest,
  CreateMessageRequest,
  CreateTaskRequest,
  MemoryEntry,
  MessageRecordPayload,
  MessagingSnapshot,
  SkillSummary,
  TaskRecord,
  WorkflowSummary,
  WorkLog,
} from './contracts';
import { MonorepoDataService } from './monorepo-data.service';
import { TaskRunnerService } from './task-runner.service';

const SOURCE = 'monorepo-controller/backend-api-services/src/controller.controller.ts';

@Controller('api/controller')
export class ControllerController {
  constructor(
    private readonly data: MonorepoDataService,
    private readonly runner: TaskRunnerService,
    private readonly applicationLogs: ApplicationLogService,
  ) {}

  @Get('snapshot')
  snapshot(): Promise<ControllerSnapshot> {
    void this.applicationLogs.writeBackendLog('DEBUG', 'Controller snapshot requested.', SOURCE);
    return this.data.snapshot();
  }

  @Get('agents')
  agents(): Promise<AgentSummary[]> {
    return this.data.agents();
  }

  @Get('skills')
  skills(): Promise<SkillSummary[]> {
    return this.data.skills();
  }

  @Post('skills')
  addSkill(@Body() payload: CreateSkillRequest): Promise<SkillSummary> {
    void this.applicationLogs.writeBackendLog('INFO', 'Controller skill creation requested.', SOURCE, { id: payload.id });
    return this.data.addSkill(payload);
  }

  @Get('workflows')
  workflows(): Promise<WorkflowSummary[]> {
    return this.data.workflows();
  }

  @Get('tasks')
  tasks(): Promise<TaskRecord[]> {
    return this.data.tasks();
  }

  @Post('tasks')
  async createTask(@Body() payload: CreateTaskRequest): Promise<TaskRecord> {
    const created = await this.data.createTask(payload);
    return created.task;
  }

  @Post('tasks/:taskId/start')
  async startTask(@Param('taskId') taskId: string): Promise<TaskRecord> {
    const launch = await this.data.prepareTaskLaunch(taskId);
    this.runner.launch(launch.task, launch.messagePath);
    return launch.task;
  }

  @Get('memory')
  memory(): Promise<MemoryEntry[]> {
    return this.data.memory();
  }

  @Get('work-logs')
  workLogs(): Promise<WorkLog[]> {
    return this.data.workLogs();
  }

  @Get('messaging')
  messaging(): Promise<MessagingSnapshot> {
    return this.data.messaging();
  }

  @Post('messages')
  async sendMessage(@Body() payload: CreateMessageRequest): Promise<MessageRecordPayload> {
    const created = await this.data.sendMessage(payload);
    if (payload.recipient === 'agent-ui-debugger' && payload.type === 'ui_debug_request') {
      this.runner.runHubOnce();
    }
    return created.record;
  }

  @Get('messaging/:messageId/thread')
  messageThread(@Param('messageId') messageId: string): Promise<MessageRecordPayload[]> {
    return this.data.messageThread(messageId);
  }
}
