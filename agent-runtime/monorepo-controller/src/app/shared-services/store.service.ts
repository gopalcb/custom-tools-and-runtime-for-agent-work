import { Injectable, inject, signal } from '@angular/core';
import { catchError, of, tap, timer } from 'rxjs';
import { HttpService } from './http.service';
import { Agent, ControllerSnapshot, CreateMessageRequest, CreateSkillRequest, CreateTaskRequest, MemoryEntry, MessageRecord, MessagingSnapshot, Skill, Task, Workflow, WorkLog } from './interfaces';

@Injectable({ providedIn: 'root' })
export class StoreService {
  private readonly http = inject(HttpService);
  readonly tasks = signal<Task[]>([]);
  readonly agents = signal<Agent[]>([]);
  readonly skills = signal<Skill[]>([]);
  readonly workflows = signal<Workflow[]>([]);
  readonly memory = signal<MemoryEntry[]>([]);
  readonly workLogs = signal<WorkLog[]>([]);
  readonly messaging = signal<MessagingSnapshot | null>(null);
  readonly selectedTaskId = signal('');
  readonly selectedAgentId = signal('');
  readonly selectedSkillId = signal('');
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    this.refresh();
    timer(3000, 3000).subscribe(() => this.refresh(false));
  }

  selectTask(id: string): void { this.selectedTaskId.set(id); }
  selectAgent(id: string): void { this.selectedAgentId.set(id); }
  selectSkill(id: string): void { this.selectedSkillId.set(id); }

  refresh(showLoading = true): void {
    if (showLoading) this.loading.set(true);
    this.http.snapshot().pipe(
      catchError((error: unknown) => {
        this.error.set(this.errorMessage(error));
        return of(null);
      }),
    ).subscribe((snapshot) => {
      if (showLoading) this.loading.set(false);
      if (!snapshot) return;
      this.applySnapshot(snapshot);
      this.error.set(null);
    });
  }

  createTask(payload: CreateTaskRequest) {
    this.saving.set(true);
    return this.http.createTask(payload).pipe(
      tap((task) => {
        this.upsertTask(task);
        this.selectedTaskId.set(task.id);
        this.saving.set(false);
        this.refresh(false);
      }),
      catchError((error: unknown) => {
        this.saving.set(false);
        this.error.set(this.errorMessage(error));
        return of(null);
      }),
    );
  }

  startTask(taskId: string) {
    this.saving.set(true);
    return this.http.startTask(taskId).pipe(
      tap((task) => {
        this.upsertTask(task);
        this.selectedTaskId.set(task.id);
        this.saving.set(false);
        this.refresh(false);
      }),
      catchError((error: unknown) => {
        this.saving.set(false);
        this.error.set(this.errorMessage(error));
        return of(null);
      }),
    );
  }

  addSkill(payload: CreateSkillRequest) {
    this.saving.set(true);
    return this.http.addSkill(payload).pipe(
      tap((skill) => {
        this.skills.update((skills) => [skill, ...skills.filter((item) => item.id !== skill.id)]);
        this.selectedSkillId.set(skill.id);
        this.saving.set(false);
        this.refresh(false);
      }),
      catchError((error: unknown) => {
        this.saving.set(false);
        this.error.set(this.errorMessage(error));
        return of(null);
      }),
    );
  }

  sendMessage(payload: CreateMessageRequest) {
    this.saving.set(true);
    return this.http.sendMessage(payload).pipe(
      tap(() => {
        this.saving.set(false);
        this.refresh(false);
      }),
      catchError((error: unknown) => {
        this.saving.set(false);
        this.error.set(this.errorMessage(error));
        return of(null);
      }),
    );
  }

  private applySnapshot(snapshot: ControllerSnapshot): void {
    this.tasks.set(snapshot.tasks);
    this.agents.set(snapshot.agents);
    this.skills.set(snapshot.skills);
    this.workflows.set(snapshot.workflows);
    this.memory.set(snapshot.memory);
    this.workLogs.set(snapshot.workLogs);
    this.messaging.set(snapshot.messaging);
    if (!this.selectedTaskId() && snapshot.tasks[0]) this.selectedTaskId.set(snapshot.tasks[0].id);
    if (!this.selectedAgentId() && snapshot.agents[0]) this.selectedAgentId.set(snapshot.agents[0].id);
    if (!this.selectedSkillId() && snapshot.skills[0]) this.selectedSkillId.set(snapshot.skills[0].id);
  }

  private upsertTask(task: Task): void {
    this.tasks.update((tasks) => [task, ...tasks.filter((item) => item.id !== task.id)]);
  }

  private errorMessage(error: unknown): string {
    if (error instanceof Error) return error.message;
    if (typeof error === 'object' && error && 'message' in error) return String((error as { message?: unknown }).message);
    return String(error);
  }
}
