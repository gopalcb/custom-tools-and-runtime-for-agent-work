import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { BACKEND_URL } from './backend-url';
import { Agent, ControllerSnapshot, CreateMessageRequest, CreateSkillRequest, CreateTaskRequest, MemoryEntry, MessageRecord, MessagingSnapshot, Skill, Task, Workflow, WorkLog } from './interfaces';

@Injectable({ providedIn: 'root' })
export class HttpService {
  private readonly baseUrl = `${BACKEND_URL}/api/controller`;

  constructor(private readonly http: HttpClient) {}

  snapshot(): Observable<ControllerSnapshot> {
    return this.http.get<ControllerSnapshot>(`${this.baseUrl}/snapshot`);
  }

  tasks(): Observable<Task[]> {
    return this.http.get<Task[]>(`${this.baseUrl}/tasks`);
  }

  createTask(payload: CreateTaskRequest): Observable<Task> {
    return this.http.post<Task>(`${this.baseUrl}/tasks`, payload);
  }

  startTask(taskId: string): Observable<Task> {
    return this.http.post<Task>(`${this.baseUrl}/tasks/${encodeURIComponent(taskId)}/start`, {});
  }

  agents(): Observable<Agent[]> {
    return this.http.get<Agent[]>(`${this.baseUrl}/agents`);
  }

  skills(): Observable<Skill[]> {
    return this.http.get<Skill[]>(`${this.baseUrl}/skills`);
  }

  addSkill(payload: CreateSkillRequest): Observable<Skill> {
    return this.http.post<Skill>(`${this.baseUrl}/skills`, payload);
  }

  workflows(): Observable<Workflow[]> {
    return this.http.get<Workflow[]>(`${this.baseUrl}/workflows`);
  }

  memory(): Observable<MemoryEntry[]> {
    return this.http.get<MemoryEntry[]>(`${this.baseUrl}/memory`);
  }

  workLogs(): Observable<WorkLog[]> {
    return this.http.get<WorkLog[]>(`${this.baseUrl}/work-logs`);
  }

  messaging(): Observable<MessagingSnapshot> {
    return this.http.get<MessagingSnapshot>(`${this.baseUrl}/messaging`);
  }

  sendMessage(payload: CreateMessageRequest): Observable<MessageRecord> {
    return this.http.post<MessageRecord>(`${this.baseUrl}/messages`, payload);
  }

  messageThread(messageId: string): Observable<MessageRecord[]> {
    return this.http.get<MessageRecord[]>(`${this.baseUrl}/messaging/${encodeURIComponent(messageId)}/thread`);
  }
}
