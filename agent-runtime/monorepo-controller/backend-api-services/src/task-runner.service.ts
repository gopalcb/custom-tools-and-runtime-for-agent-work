import { Injectable } from '@nestjs/common';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { ApplicationLogService } from './application-log.service';
import { TaskRecord } from './contracts';
import { findProjectRoot } from './project-paths';

const SOURCE = 'monorepo-controller/backend-api-services/src/task-runner.service.ts';

@Injectable()
export class TaskRunnerService {
  private readonly root = findProjectRoot();

  constructor(private readonly applicationLogs: ApplicationLogService) {}

  launch(task: TaskRecord, messagePath: string): void {
    const python = resolve(this.root, '.venv', 'bin', 'python');
    if (!existsSync(python)) {
      void this.applicationLogs.writeBackendLog('ERROR', 'Unable to launch task runner because .venv Python is missing.', SOURCE, { taskId: task.id });
      return;
    }
    const pythonPath = this.pythonPath();
    const child = spawn(
      python,
      [
        '-m',
        'agent_monorepo.task_runner',
        '--project-root',
        this.root,
        '--message-path',
        messagePath,
        '--task-id',
        task.id,
        '--agent-id',
        task.agentId,
        '--run-id',
        `run-${task.id}`,
        '--session-id',
        `session-${task.id}`,
      ],
      {
        cwd: this.root,
        detached: true,
        stdio: 'ignore',
        env: { ...process.env, PYTHONPATH: pythonPath },
      },
    );
    child.unref();
    void this.applicationLogs.writeBackendLog('INFO', `Launched task runner for ${task.id}.`, SOURCE, {
      pid: child.pid,
      agentId: task.agentId,
      messagePath,
    });
  }

  runHubOnce(): void {
    const python = resolve(this.root, '.venv', 'bin', 'python');
    if (!existsSync(python)) {
      void this.applicationLogs.writeBackendLog('ERROR', 'Unable to launch message hub because .venv Python is missing.', SOURCE);
      return;
    }
    const pythonPath = this.pythonPath();
    const child = spawn(
      python,
      ['-m', 'agents_internal_messaging.hub', '--root', resolve(this.root, '.agent-state', 'agents-messaging'), 'run-once'],
      {
        cwd: this.root,
        detached: true,
        stdio: 'ignore',
        env: { ...process.env, PYTHONPATH: pythonPath },
      },
    );
    child.unref();
    void this.applicationLogs.writeBackendLog('INFO', 'Launched message hub for one dispatch pass.', SOURCE, { pid: child.pid });
  }

  private pythonPath(): string {
    return [
      resolve(this.root, 'agent-runtime', 'agent-monorepo'),
      resolve(this.root, 'agent-tools', 'internal-messaging'),
      resolve(this.root, 'agent-tools', 'ui-debugger'),
      resolve(this.root, 'agent-gateway'),
      process.env['PYTHONPATH'] ?? '',
    ].filter(Boolean).join(':');
  }
}
