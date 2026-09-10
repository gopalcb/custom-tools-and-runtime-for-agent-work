import { Injectable } from '@angular/core';
import { Observable, delay, of } from 'rxjs';
import { AppRequest, AppResponse } from './interfaces';
import { mockAgents, mockMemory, mockSkills, mockTasks, mockWorkflows, mockWorkLogs } from './mock-data';

@Injectable({ providedIn: 'root' })
export class HttpService {
  request<TData = unknown, TPayload = unknown>(request: AppRequest<TPayload>): Observable<AppResponse<TData>> {
    const data: Record<string, unknown> = { '/tasks': mockTasks, '/agents': mockAgents, '/skills': mockSkills, '/workflows': mockWorkflows, '/memory': mockMemory, '/work-logs': mockWorkLogs };
    return of({ success: true, status: 200, message: 'Mock response', data: data[request.endpoint] as TData, timestamp: new Date().toISOString() }).pipe(delay(120));
  }
}
