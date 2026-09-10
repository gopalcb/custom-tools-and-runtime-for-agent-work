export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type AppRequest<TPayload = unknown> = { readonly endpoint: string; readonly method: HttpMethod; readonly payload?: TPayload };
export type AppResponse<TData = unknown> = { readonly success: boolean; readonly status: number; readonly message: string; readonly data: TData; readonly timestamp: string };

export type TaskStatus = 'awaiting implementation' | 'implementing' | 'complete' | 'need rework';
export type Task = { id: string; title: string; summary: string; status: TaskStatus; date: string; tokens: number; plan: string; owner: string; duration: string };
export type Agent = { id: string; name: string; role: string; status: string; summary: string; skills: string[]; history: string[]; performance: { label: string; value: string }[] };
export type Skill = { id: string; name: string; category: string; summary: string; content: string };
export type Workflow = { name: string; status: string; runs: string; owner: string; description: string };
export type MemoryEntry = { title: string; kind: string; updated: string; excerpt: string };
export type WorkLog = { date: string; event: string; agent: string; detail: string };
export type CodexTurnRequest = { prompt: string; thread_id?: string; sandbox?: 'read_only' | 'workspace_write' | 'full_access'; model?: string; ephemeral?: boolean };
export type CodexTurnReference = { thread_id: string; turn_id: string };
export type CodexSocketEvent = { turnId: string; event: Record<string, unknown> };
