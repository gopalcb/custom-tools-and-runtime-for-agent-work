/** Shared HTTP payloads for the monorepo controller. */

export type TaskStatus = 'awaiting implementation' | 'implementing' | 'complete' | 'need rework';

export interface TaskEvent {
  ts: string;
  type: string;
  status?: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface TaskRecord {
  id: string;
  title: string;
  summary: string;
  status: TaskStatus;
  label?: string;
  date: string;
  tokens: number;
  plan: string;
  owner: string;
  agentId: string;
  duration: string;
  prompt: string;
  messageId?: string;
  runId?: string;
  sessionId?: string;
  createdAt: string;
  updatedAt: string;
  events: TaskEvent[];
  source?: string;
  planId?: string;
  planTitle?: string;
  plannedTaskId?: string;
  messagePath?: string;
  taskPath?: string;
  tasksYamlPath?: string;
  description?: string;
  files?: string[];
  dependsOn?: string[];
  acceptanceCriteria?: string[];
}

export interface CreateTaskRequest {
  title?: string;
  prompt?: string;
  agentId?: string;
  planId?: string;
  planTitle?: string;
  plannedTaskId?: string;
}

export interface AgentSummary {
  id: string;
  name: string;
  role: string;
  status: string;
  summary: string;
  workflow: string;
  tools: string[];
  aliases: string[];
  instructionsPath: string;
  skills: string[];
  history: string[];
  performance: { label: string; value: string }[];
}

export interface SkillSummary {
  id: string;
  name: string;
  category: string;
  summary: string;
  content: string;
  path: string;
  assignedAgents: string[];
}

export interface CreateSkillRequest {
  id?: string;
  name?: string;
  category?: string;
  summary?: string;
  content?: string;
  assignToAgentIds?: string[];
}

export interface WorkflowSummary {
  id: string;
  name: string;
  status: string;
  runs: string;
  owner: string;
  description: string;
  phase: string;
  steps: { id: string; name: string; uses: string; agent?: string; tool?: string; command?: string }[];
}

export interface MemoryEntry {
  id: string;
  title: string;
  kind: string;
  status: string;
  updated: string;
  excerpt: string;
  content?: string;
  path: string;
  runId?: string;
  sessionId?: string;
  tags: string[];
  metadata?: Record<string, unknown>;
}

export interface WorkLog {
  id: string;
  date: string;
  event: string;
  agent: string;
  detail: string;
  status?: string;
  path?: string;
}

export interface MessageRecordPayload {
  id: string;
  created_at: string;
  updated_at: string;
  sender: string;
  recipient: string;
  type: string;
  reply_to?: string | null;
  status: string;
  path: string;
  folder_agent_id: string;
  payload?: Record<string, unknown>;
  error?: string;
}

export interface OperationalErrorRecord {
  id: string;
  status: string;
  fingerprint: string;
  created_at: string;
  updated_at: string;
  occurrence_count?: number;
  error?: Record<string, unknown>;
  history?: Record<string, unknown>[];
  resolution?: Record<string, unknown>;
}

export interface CreateMessageRequest {
  sender?: string;
  recipient?: string;
  type?: string;
  payload?: Record<string, unknown>;
  replyTo?: string;
}

export interface MessagingSummary {
  root: string;
  manifest: string;
  eventLog: string;
  total: number;
  tasks: number;
  unresolved: number;
  activeErrors: number;
  currentError?: OperationalErrorRecord | null;
  byStatus: Record<string, number>;
  byType: Record<string, number>;
  taskStatuses: Record<string, number>;
  agents: string[];
}

export interface MessagingSnapshot {
  summary: MessagingSummary;
  messages: MessageRecordPayload[];
  events: Record<string, unknown>[];
  errors: OperationalErrorRecord[];
}

export interface ControllerSnapshot {
  agents: AgentSummary[];
  tasks: TaskRecord[];
  skills: SkillSummary[];
  workflows: WorkflowSummary[];
  memory: MemoryEntry[];
  workLogs: WorkLog[];
  messaging: MessagingSnapshot;
}

export type ApplicationLogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

export interface RuntimeLogRequest {
  level?: string;
  source?: string;
  message?: string;
  details?: unknown;
  timestamp?: string;
  url?: string;
  userAgent?: string;
}
