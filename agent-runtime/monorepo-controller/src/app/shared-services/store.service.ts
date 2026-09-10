import { Injectable, inject, signal } from '@angular/core';
import { HttpService } from './http.service';
import { Agent, MemoryEntry, Skill, Task, Workflow, WorkLog } from './interfaces';

@Injectable({ providedIn: 'root' })
export class StoreService {
  private readonly http = inject(HttpService);
  readonly tasks = signal<Task[]>([]);
  readonly agents = signal<Agent[]>([]);
  readonly skills = signal<Skill[]>([]);
  readonly workflows = signal<Workflow[]>([]);
  readonly memory = signal<MemoryEntry[]>([]);
  readonly workLogs = signal<WorkLog[]>([]);
  readonly selectedTaskId = signal('task-ui');
  readonly selectedAgentId = signal('runtime-architect');
  readonly selectedSkillId = signal('context-standard');

  constructor() {
    this.http.request<Task[]>({ endpoint: '/tasks', method: 'GET' }).subscribe((response) => this.tasks.set(response.data));
    this.http.request<Agent[]>({ endpoint: '/agents', method: 'GET' }).subscribe((response) => this.agents.set(response.data));
    this.http.request<Skill[]>({ endpoint: '/skills', method: 'GET' }).subscribe((response) => this.skills.set(response.data));
    this.http.request<Workflow[]>({ endpoint: '/workflows', method: 'GET' }).subscribe((response) => this.workflows.set(response.data));
    this.http.request<MemoryEntry[]>({ endpoint: '/memory', method: 'GET' }).subscribe((response) => this.memory.set(response.data));
    this.http.request<WorkLog[]>({ endpoint: '/work-logs', method: 'GET' }).subscribe((response) => this.workLogs.set(response.data));
  }

  selectTask(id: string): void { this.selectedTaskId.set(id); }
  selectAgent(id: string): void { this.selectedAgentId.set(id); }
  selectSkill(id: string): void { this.selectedSkillId.set(id); }
}
