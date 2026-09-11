import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdir, readdir, readFile, rename, writeFile } from 'node:fs/promises';
import { basename, dirname, relative, resolve } from 'node:path';
import { parse, stringify } from 'yaml';
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
  MessagingSummary,
  OperationalErrorRecord,
  SkillSummary,
  TaskEvent,
  TaskRecord,
  TaskStatus,
  WorkflowSummary,
  WorkLog,
} from './contracts';
import { asRecord, asStringArray, findProjectRoot, safeJoin } from './project-paths';

const SOURCE = 'monorepo-controller/backend-api-services/src/monorepo-data.service.ts';
const IDENTIFIER = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_ITEMS = 300;

type MessageFile = {
  id: string;
  created_at: string;
  sender: string;
  recipient: string;
  type: string;
  payload: Record<string, unknown>;
  reply_to?: string | null;
};

@Injectable()
export class MonorepoDataService {
  readonly root = findProjectRoot();
  readonly messageRoot = safeJoin(this.root, '.agent-state', 'agents-messaging');
  readonly stateRoot = safeJoin(this.root, '.agent-state');
  readonly plannedTasksRoot = safeJoin(this.root, 'agent-runtime', 'controller-data-store', 'planned-tasks');

  constructor(private readonly applicationLogs: ApplicationLogService) {}

  async snapshot(): Promise<ControllerSnapshot> {
    const [agents, tasks, skills, workflows, memory, workLogs, messaging] = await Promise.all([
      this.agents(),
      this.tasks(),
      this.skills(),
      this.workflows(),
      this.memory(),
      this.workLogs(),
      this.messaging(),
    ]);
    return { agents, tasks, skills, workflows, memory, workLogs, messaging };
  }

  async agents(): Promise<AgentSummary[]> {
    await this.ensureMessagingRoot();
    const registry = await this.registry();
    const agentsRoot = this.configuredPath(registry, ['paths', 'agents'], 'agent-config/agents');
    const tasks = await this.tasks();
    const messageRecords = await this.messageRecords();
    const runStats = await this.runStatsByAgent();
    const entries = await readdir(agentsRoot, { withFileTypes: true }).catch(() => []);
    const agents: AgentSummary[] = [];
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const agentYamlPath = resolve(agentsRoot, entry.name, 'agent.yaml');
      if (!existsSync(agentYamlPath)) continue;
      const raw = await this.readYaml(agentYamlPath);
      if (raw['disabled'] === true) continue;
      const id = String(raw['id'] ?? entry.name);
      const instructionsPath = resolve(agentsRoot, entry.name, String(raw['instructions'] ?? 'instructions.md'));
      const instructions = existsSync(instructionsPath) ? await readFile(instructionsPath, 'utf-8') : '';
      const activeTasks = tasks.filter((task) => task.agentId === id && task.status === 'implementing').length;
      const pendingMessages = messageRecords.filter((record) => record.recipient === id && record.status === 'pending').length;
      const stats = runStats.get(id) ?? { runs: 0, completed: 0 };
      agents.push({
        id,
        name: String(raw['name'] ?? id),
        role: String(raw['description'] ?? 'Agent runtime participant'),
        status: activeTasks > 0 ? 'implementing' : pendingMessages > 0 ? 'queued' : 'available',
        summary: this.firstMeaningfulLine(instructions) || String(raw['description'] ?? id),
        workflow: String(raw['workflow'] ?? 'default'),
        tools: asStringArray(raw['tools']),
        aliases: asStringArray(raw['aliases']),
        instructionsPath: this.relativePath(instructionsPath),
        skills: asStringArray(raw['skills']),
        history: await this.agentHistory(id),
        performance: [
          { label: 'Runs', value: String(stats.runs) },
          { label: 'Completed', value: String(stats.completed) },
          { label: 'Pending', value: String(pendingMessages) },
        ],
      });
    }
    agents.sort((left, right) => left.name.localeCompare(right.name));
    return agents;
  }

  async skills(): Promise<SkillSummary[]> {
    const registry = await this.registry();
    const agents = await this.agentYamlSummaries();
    const roots = this.skillRoots(registry);
    const paths: string[] = [];
    for (const root of roots) {
      paths.push(...(await this.findFiles(root, (path) => basename(path) === 'SKILL.md')));
    }
    const skills: SkillSummary[] = [];
    for (const path of paths.sort()) {
      const content = await readFile(path, 'utf-8');
      const id = basename(dirname(path));
      const assignedAgents = agents.filter((agent) => agent.skills.includes(id)).map((agent) => agent.id);
      skills.push({
        id,
        name: this.markdownTitle(content) || id,
        category: basename(dirname(dirname(path))) || 'skills',
        summary: this.firstParagraph(content),
        content,
        path: this.relativePath(path),
        assignedAgents,
      });
    }
    return skills;
  }

  async addSkill(payload: CreateSkillRequest): Promise<SkillSummary> {
    const id = this.safeIdentifier(payload.id, 'skill id');
    if ((await this.skills()).some((skill) => skill.id === id)) {
      throw new BadRequestException(`Skill already exists: ${id}`);
    }
    const name = String(payload.name || id);
    const summary = String(payload.summary || 'Custom controller-added skill.').trim();
    const category = this.safeIdentifier(payload.category || 'custom', 'skill category');
    const content = String(payload.content || `# ${name}\n\n${summary}\n`).trimEnd() + '\n';
    const registry = await this.registry();
    const skillsRoot = this.skillRoots(registry)[0] ?? safeJoin(this.root, 'agent-config', 'skills');
    const target = safeJoin(skillsRoot, category, id, 'SKILL.md');
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, content, 'utf-8');

    const assignTo = payload.assignToAgentIds ?? [];
    for (const agentId of assignTo) {
      await this.addSkillToAgent(agentId, id);
    }
    void this.applicationLogs.writeBackendLog('INFO', `Skill ${id} added from controller UI.`, SOURCE, {
      path: this.relativePath(target),
      assignTo,
    });
    const created = (await this.skills()).find((skill) => skill.id === id);
    if (!created) throw new NotFoundException(`Created skill ${id} was not found`);
    return created;
  }

  async workflows(): Promise<WorkflowSummary[]> {
    const registry = await this.registry();
    const workflowPath = this.configuredPath(registry, ['paths', 'workflows'], 'agent-runtime/agent-monorepo/workflows/workflow-orchestrator.yaml');
    const workflowStepsPath = this.configuredPath(registry, ['paths', 'workflow_steps'], 'agent-runtime/agent-monorepo/workflows/workflow-steps.yaml');
    const workflowDocument = await this.readYaml(workflowPath);
    const stepDocument = await this.readYaml(workflowStepsPath);
    const workflows = asRecord(workflowDocument['workflows']);
    const stepCatalog = asRecord(stepDocument['steps']);
    const defaultWorkflow = String(asRecord(registry['runtime'])['default_workflow'] ?? 'default');
    const counts = await this.workflowRunCounts();
    return Object.entries(workflows).map(([id, rawWorkflow]) => {
      const workflow = asRecord(rawWorkflow);
      const steps = Array.isArray(workflow['steps']) ? workflow['steps'] : [];
      const expanded = steps.map((rawStep) => {
        const step = asRecord(rawStep);
        const ref = typeof step['ref'] === 'string' ? step['ref'] : '';
        return { ...asRecord(stepCatalog[ref]), ...step };
      });
      return {
        id,
        name: id,
        status: id === defaultWorkflow ? 'default' : String(workflow['phase'] ?? 'execution'),
        runs: `${counts.get(id) ?? 0} runs`,
        owner: String(workflow['phase'] ?? 'execution'),
        description: expanded.map((step) => String(step['name'] ?? step['id'] ?? 'step')).join(' -> '),
        phase: String(workflow['phase'] ?? 'execution'),
        steps: expanded.map((step) => ({
          id: String(step['id'] ?? step['ref'] ?? 'step'),
          name: String(step['name'] ?? step['id'] ?? 'Step'),
          uses: String(step['uses'] ?? 'unknown'),
          agent: typeof step['agent'] === 'string' ? step['agent'] : undefined,
          tool: typeof step['tool'] === 'string' ? step['tool'] : undefined,
          command: typeof step['command'] === 'string' ? step['command'] : undefined,
        })),
      };
    });
  }

  async tasks(): Promise<TaskRecord[]> {
    await this.ensureMessagingRoot();
    const directory = resolve(this.messageRoot, 'records', 'tasks');
    const paths = await this.findFiles(directory, (path) => path.endsWith('.json'));
    const tasks: TaskRecord[] = [];
    for (const path of paths) {
      const raw = await this.readJsonOptional(path);
      if (!raw) continue;
      tasks.push(await this.normalizeTask(raw));
    }
    const linkedPlannedTasks = new Set(
      tasks
        .filter((task) => task.planId && task.plannedTaskId)
        .map((task) => `${task.planId}:${task.plannedTaskId}`),
    );
    tasks.push(...(await this.plannedTasks(linkedPlannedTasks)));
    const runTasks = await this.tasksFromRuns(new Set(tasks.map((task) => task.runId).filter((value): value is string => Boolean(value))));
    tasks.push(...runTasks);
    tasks.sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
    return tasks;
  }

  async createTask(payload: CreateTaskRequest): Promise<{ task: TaskRecord; messagePath: string }> {
    await this.ensureMessagingRoot();
    const prompt = String(payload.prompt || '').trim();
    const agentId = String(payload.agentId || 'agent-monorepo').trim();
    if (!prompt) throw new BadRequestException('Task prompt is required');
    const agents = await this.agents();
    if (!agents.some((agent) => agent.id === agentId)) throw new BadRequestException(`Unknown agent: ${agentId}`);

    const createdAt = this.now();
    const taskId = this.safeIdentifier(`task-${randomUUID().slice(0, 8)}`, 'task id');
    const title = String(payload.title || this.titleFromPrompt(prompt)).trim();
    const summary = this.summaryFromPrompt(prompt);
    const message: MessageFile = {
      id: randomUUID().replace(/-/g, ''),
      created_at: createdAt,
      sender: 'monorepo-controller',
      recipient: agentId,
      type: 'task_request',
      payload: {
        task_id: taskId,
        title,
        prompt,
        requester: 'monorepo-controller',
        created_at: createdAt,
        plan_id: payload.planId,
        plan_title: payload.planTitle,
        planned_task_id: payload.plannedTaskId,
      },
    };
    const messagePath = await this.writeMessage(message);
    const event: TaskEvent = {
      ts: createdAt,
      type: 'task.created',
      status: 'awaiting implementation',
      message: `Task queued for ${agentId}. Awaiting user approval to start work.`,
      details: { message_id: message.id, message_path: this.relativePath(messagePath) },
    };
    await this.writeTaskRecord({
      id: taskId,
      title,
      summary,
      prompt,
      status: 'awaiting implementation',
      agent_id: agentId,
      owner: agentId,
      message_id: message.id,
      message_path: this.relativePath(messagePath),
      plan_id: payload.planId,
      plan_title: payload.planTitle,
      planned_task_id: payload.plannedTaskId,
      created_at: createdAt,
      updated_at: createdAt,
      plan: `Agent: ${agentId}\nStart policy: wait for explicit user approval\n\n${prompt}`,
      events: [event],
    });
    const task = (await this.tasks()).find((item) => item.id === taskId);
    if (!task) throw new NotFoundException(`Created task ${taskId} was not found`);
    void this.applicationLogs.writeBackendLog('INFO', `Task ${taskId} queued for ${agentId}.`, SOURCE);
    return { task, messagePath };
  }

  async prepareTaskLaunch(taskId: string): Promise<{ task: TaskRecord; messagePath: string }> {
    await this.ensureMessagingRoot();
    const task = (await this.tasks()).find((item) => item.id === taskId);
    if (!task) throw new NotFoundException(`Task ${taskId} was not found`);
    if (!task.messageId) throw new BadRequestException(`Task ${taskId} is not linked to a queue message`);
    const message = (await this.messageRecords()).find((item) => item.id === task.messageId);
    if (!message) throw new NotFoundException(`Message ${task.messageId} was not found`);
    if (message.status !== 'pending') throw new BadRequestException(`Task ${taskId} message is ${message.status}, not pending`);
    const messagePath = this.absolutePath(message.path);
    if (!existsSync(messagePath)) throw new NotFoundException(`Message file for task ${taskId} was not found`);
    await this.appendTaskEvent(taskId, {
      ts: this.now(),
      type: 'task.work_requested',
      status: 'awaiting implementation',
      message: 'User approved starting agent work for this task.',
      details: { message_id: message.id, message_path: this.relativePath(messagePath) },
    });
    return { task, messagePath };
  }

  async sendMessage(payload: CreateMessageRequest): Promise<{ record: MessageRecordPayload; messagePath: string }> {
    await this.ensureMessagingRoot();
    const sender = String(payload.sender || 'monorepo-controller').trim();
    const recipient = String(payload.recipient || '').trim();
    const type = String(payload.type || '').trim();
    if (!sender) throw new BadRequestException('Sender is required');
    if (!recipient) throw new BadRequestException('Recipient is required');
    if (!type) throw new BadRequestException('Message type is required');
    const createdAt = this.now();
    const message: MessageFile = {
      id: randomUUID().replace(/-/g, ''),
      created_at: createdAt,
      sender,
      recipient,
      type,
      payload: asRecord(payload.payload),
      reply_to: payload.replyTo ?? null,
    };
    const messagePath = await this.writeMessage(message);
    const record = (await this.messageRecords()).find((item) => item.id === message.id);
    if (!record) throw new NotFoundException(`Created message ${message.id} was not found`);
    void this.applicationLogs.writeBackendLog('INFO', `Message ${message.id} sent to ${recipient}.`, SOURCE, { type });
    return { record, messagePath };
  }

  async messaging(): Promise<MessagingSnapshot> {
    await this.ensureMessagingRoot();
    const [messages, tasks, events] = await Promise.all([
      this.messageRecords(),
      this.tasks(),
      this.readJsonl(resolve(this.messageRoot, 'records', 'events.jsonl'), MAX_ITEMS),
    ]);
    const errors = await this.errorRecords();
    const currentError = errors.find((error) => error.status === 'active') ?? null;
    const byStatus: Record<string, number> = {};
    const byType: Record<string, number> = {};
    const taskStatuses: Record<string, number> = {};
    const agents = new Set<string>();
    for (const message of messages) {
      byStatus[message.status] = (byStatus[message.status] ?? 0) + 1;
      byType[message.type] = (byType[message.type] ?? 0) + 1;
      agents.add(message.sender);
      agents.add(message.recipient);
    }
    for (const task of tasks) {
      taskStatuses[task.status] = (taskStatuses[task.status] ?? 0) + 1;
    }
    const summary: MessagingSummary = {
      root: this.messageRoot,
      manifest: resolve(this.messageRoot, 'manifest.json'),
      eventLog: resolve(this.messageRoot, 'records', 'events.jsonl'),
      total: messages.length,
      tasks: tasks.length,
      unresolved: messages.filter((message) => message.status === 'pending').length,
      activeErrors: errors.filter((error) => error.status === 'active').length,
      currentError,
      byStatus,
      byType,
      taskStatuses,
      agents: [...agents].filter(Boolean).sort(),
    };
    return { summary, messages, events, errors };
  }

  private async errorRecords(): Promise<OperationalErrorRecord[]> {
    const records: OperationalErrorRecord[] = [];
    const currentPath = resolve(this.messageRoot, 'current-error.json');
    if (existsSync(currentPath)) {
      const current = await this.readJsonOptional(currentPath);
      if (current) records.push(this.errorRecord(current));
    }
    const archiveRoot = resolve(this.messageRoot, 'errors');
    const archivedPaths = await this.findFiles(archiveRoot, (path) => path.endsWith('.json'));
    for (const path of archivedPaths) {
      const raw = await this.readJsonOptional(path);
      if (raw) records.push(this.errorRecord(raw));
    }
    records.sort((left, right) => right.updated_at.localeCompare(left.updated_at));
    return records.slice(0, MAX_ITEMS);
  }

  private errorRecord(raw: Record<string, unknown>): OperationalErrorRecord {
    return {
      id: String(raw['id'] ?? ''),
      status: String(raw['status'] ?? 'unknown'),
      fingerprint: String(raw['fingerprint'] ?? ''),
      created_at: String(raw['created_at'] ?? ''),
      updated_at: String(raw['updated_at'] ?? raw['created_at'] ?? ''),
      occurrence_count: typeof raw['occurrence_count'] === 'number' ? raw['occurrence_count'] : undefined,
      error: asRecord(raw['error']),
      history: Array.isArray(raw['history']) ? raw['history'].map((item) => asRecord(item)) : undefined,
      resolution: raw['resolution'] ? asRecord(raw['resolution']) : undefined,
    };
  }

  async messageThread(messageId: string): Promise<MessageRecordPayload[]> {
    const records = await this.messageRecords();
    const byId = new Map(records.map((record) => [record.id, record]));
    if (!byId.has(messageId)) throw new NotFoundException(`Message ${messageId} was not found`);
    let rootId = messageId;
    while (byId.get(rootId)?.reply_to && byId.has(String(byId.get(rootId)?.reply_to))) {
      rootId = String(byId.get(rootId)?.reply_to);
    }
    const ids = new Set([rootId]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const record of records) {
        if (record.reply_to && ids.has(record.reply_to) && !ids.has(record.id)) {
          ids.add(record.id);
          changed = true;
        }
      }
    }
    return records.filter((record) => ids.has(record.id)).sort((left, right) => left.created_at.localeCompare(right.created_at));
  }

  async memory(): Promise<MemoryEntry[]> {
    const memoryRoot = safeJoin(this.stateRoot, 'cache', 'memory', 'records');
    const paths = await this.findFiles(memoryRoot, (path) => path.endsWith('.json'));
    const entries: MemoryEntry[] = [];
    for (const path of paths) {
      const raw = await this.readJsonOptional(path);
      if (!raw) continue;
      const content = String(raw['content'] ?? '');
      const metadata = asRecord(raw['metadata']);
      const tags = asStringArray(metadata['tags']);
      entries.push({
        id: String(raw['id'] ?? basename(path, '.json')),
        title: String(metadata['title'] ?? raw['id'] ?? basename(path, '.json')),
        kind: String(metadata['kind'] ?? 'memory'),
        status: String(metadata['status'] ?? 'stored'),
        updated: String(metadata['updated_at'] ?? metadata['created_at'] ?? ''),
        excerpt: content.slice(0, 900),
        content,
        path: this.relativePath(path),
        runId: typeof metadata['run_id'] === 'string' ? metadata['run_id'] : undefined,
        sessionId: typeof metadata['session_id'] === 'string' ? metadata['session_id'] : undefined,
        tags,
        metadata,
      });
    }
    entries.sort((left, right) => right.updated.localeCompare(left.updated));
    return entries;
  }

  async workLogs(): Promise<WorkLog[]> {
    const runtimeEvents = await this.runtimeWorkLogs();
    const messageEvents = (await this.readJsonl(resolve(this.messageRoot, 'records', 'events.jsonl'), MAX_ITEMS)).map((event, index) => ({
      id: `message-${index}-${String(event['message_id'] ?? event['task_id'] ?? index)}`,
      date: this.displayDate(String(event['event_at'] ?? '')),
      event: String(event['event'] ?? 'message.event'),
      agent: String(event['recipient'] ?? event['agent_id'] ?? event['sender'] ?? 'messaging'),
      detail: this.messageEventDetail(event),
      status: String(event['status'] ?? event['message_type'] ?? ''),
      path: typeof event['status_path'] === 'string' ? this.relativePath(event['status_path']) : undefined,
    }));
    return [...messageEvents, ...runtimeEvents]
      .sort((left, right) => right.date.localeCompare(left.date))
      .slice(0, MAX_ITEMS);
  }

  private async registry(): Promise<Record<string, unknown>> {
    return this.readYaml(safeJoin(this.root, 'project-registry.yaml'));
  }

  private async readYaml(path: string): Promise<Record<string, unknown>> {
    const value = parse(await readFile(path, 'utf-8')) as unknown;
    return asRecord(value);
  }

  private async readJson(path: string): Promise<Record<string, unknown>> {
    const value = JSON.parse(await readFile(path, 'utf-8')) as unknown;
    return asRecord(value);
  }

  private async readJsonOptional(path: string): Promise<Record<string, unknown> | null> {
    try {
      return await this.readJson(path);
    } catch (error) {
      void this.applicationLogs.writeBackendLog('WARN', `Skipping unreadable JSON record: ${this.relativePath(path)}`, SOURCE, {
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }
  }

  private async readJsonl(path: string, limit: number): Promise<Record<string, unknown>[]> {
    if (!existsSync(path)) return [];
    const lines = (await readFile(path, 'utf-8')).split('\n').filter((line) => line.trim());
    const events: Record<string, unknown>[] = [];
    for (const line of lines.slice(-limit).reverse()) {
      try {
        events.push(asRecord(JSON.parse(line)));
      } catch {
        continue;
      }
    }
    return events;
  }

  private configuredPath(registry: Record<string, unknown>, keys: [string, string], fallback: string): string {
    const group = asRecord(registry[keys[0]]);
    const rawValue = group[keys[1]];
    const value = typeof rawValue === 'string' ? rawValue : fallback;
    return safeJoin(this.root, value);
  }

  private skillRoots(registry: Record<string, unknown>): string[] {
    const paths = asRecord(registry['paths']);
    const configured = paths['skills'];
    if (Array.isArray(configured)) return configured.filter((item): item is string => typeof item === 'string').map((item) => safeJoin(this.root, item));
    if (typeof configured === 'string') return [safeJoin(this.root, configured)];
    return [safeJoin(this.root, 'agent-config', 'skills')];
  }

  private async agentYamlSummaries(): Promise<{ id: string; skills: string[] }[]> {
    const registry = await this.registry();
    const agentsRoot = this.configuredPath(registry, ['paths', 'agents'], 'agent-config/agents');
    const entries = await readdir(agentsRoot, { withFileTypes: true }).catch(() => []);
    const agents: { id: string; skills: string[] }[] = [];
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const agentYamlPath = resolve(agentsRoot, entry.name, 'agent.yaml');
      if (!existsSync(agentYamlPath)) continue;
      const raw = await this.readYaml(agentYamlPath);
      agents.push({ id: String(raw['id'] ?? entry.name), skills: asStringArray(raw['skills']) });
    }
    return agents;
  }

  private async addSkillToAgent(agentId: string, skillId: string): Promise<void> {
    const registry = await this.registry();
    const agentsRoot = this.configuredPath(registry, ['paths', 'agents'], 'agent-config/agents');
    const agentPath = safeJoin(agentsRoot, agentId, 'agent.yaml');
    if (!existsSync(agentPath)) throw new BadRequestException(`Unknown agent: ${agentId}`);
    const raw = await this.readYaml(agentPath);
    const skills = asStringArray(raw['skills']);
    if (!skills.includes(skillId)) raw['skills'] = [...skills, skillId];
    await writeFile(agentPath, stringify(raw), 'utf-8');
  }

  private async messageRecords(): Promise<MessageRecordPayload[]> {
    await this.ensureMessagingRoot();
    const directory = resolve(this.messageRoot, 'records', 'messages');
    const paths = await this.findFiles(directory, (path) => path.endsWith('.json'));
    const records: MessageRecordPayload[] = [];
    for (const path of paths) {
      const raw = await this.readJsonOptional(path);
      if (!raw) continue;
      records.push({
        id: String(raw['id'] ?? basename(path, '.json')),
        created_at: String(raw['created_at'] ?? ''),
        updated_at: String(raw['updated_at'] ?? raw['created_at'] ?? ''),
        sender: String(raw['sender'] ?? ''),
        recipient: String(raw['recipient'] ?? ''),
        type: String(raw['type'] ?? ''),
        reply_to: typeof raw['reply_to'] === 'string' ? raw['reply_to'] : null,
        status: String(raw['status'] ?? 'unknown'),
        path: String(raw['path'] ?? ''),
        folder_agent_id: String(raw['folder_agent_id'] ?? ''),
        payload: asRecord(raw['payload']),
        error: typeof raw['error'] === 'string' ? raw['error'] : undefined,
      });
    }
    records.sort((left, right) => right.created_at.localeCompare(left.created_at));
    return records;
  }

  private async writeMessage(message: MessageFile): Promise<string> {
    const recipientDir = resolve(this.messageRoot, 'inbox', message.recipient);
    await mkdir(recipientDir, { recursive: true });
    const fileName = `${message.created_at.replace(/[:.]/g, '')}-${message.id}.json`;
    const messagePath = resolve(recipientDir, fileName);
    await this.writeJsonAtomic(messagePath, message);
    const record = {
      id: message.id,
      created_at: message.created_at,
      updated_at: message.created_at,
      sender: message.sender,
      recipient: message.recipient,
      type: message.type,
      reply_to: message.reply_to ?? null,
      status: 'pending',
      path: messagePath,
      folder_agent_id: message.recipient,
      payload: message.payload,
    };
    await this.writeJsonAtomic(resolve(this.messageRoot, 'records', 'messages', `${message.id}.json`), record);
    await this.appendMessagingEvent({
      event: 'sent',
      event_at: this.now(),
      message_id: message.id,
      message_type: message.type,
      sender: message.sender,
      recipient: message.recipient,
      reply_to: message.reply_to ?? null,
      status_path: messagePath,
      folder_agent_id: message.recipient,
      payload: message.payload,
    });
    return messagePath;
  }

  private async writeTaskRecord(task: Record<string, unknown>): Promise<void> {
    const id = String(task['id'] ?? '');
    await this.writeJsonAtomic(resolve(this.messageRoot, 'records', 'tasks', `${id}.json`), task);
    await this.appendMessagingEvent({
      event: 'task.updated',
      event_at: this.now(),
      task_id: id,
      status: task['status'],
      agent_id: task['agent_id'],
      message_id: task['message_id'],
      run_id: task['run_id'],
      session_id: task['session_id'],
    });
  }

  private async appendTaskEvent(taskId: string, event: TaskEvent): Promise<void> {
    const path = resolve(this.messageRoot, 'records', 'tasks', `${taskId}.json`);
    const raw = await this.readJsonOptional(path);
    if (!raw) throw new NotFoundException(`Task ${taskId} was not found`);
    const events = Array.isArray(raw['events']) ? raw['events'].map((item) => asRecord(item)) : [];
    raw['events'] = [...events, event];
    raw['updated_at'] = event.ts;
    await this.writeTaskRecord(raw);
  }

  private async appendMessagingEvent(event: Record<string, unknown>): Promise<void> {
    const path = resolve(this.messageRoot, 'records', 'events.jsonl');
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, `${JSON.stringify(event)}\n`, { encoding: 'utf-8', flag: 'a' });
  }

  private async normalizeTask(raw: Record<string, unknown>): Promise<TaskRecord> {
    const runId = this.stringValue(raw['run_id'] ?? raw['runId']);
    const sessionId = this.stringValue(raw['session_id'] ?? raw['sessionId']);
    const runMetadata = runId && sessionId ? await this.runMetadata(sessionId, runId) : {};
    const isPlannedTask = raw['label'] === 'planned-task' || raw['source'] === 'planned-task' || Boolean(raw['planned_task_id'] ?? raw['plannedTaskId']);
    const status = this.taskStatus(String((isPlannedTask ? raw['status'] : runMetadata['status']) ?? raw['status'] ?? 'awaiting implementation'));
    const createdAt = String(raw['created_at'] ?? raw['createdAt'] ?? runMetadata['started_at'] ?? this.now());
    const updatedAt = String(raw['updated_at'] ?? raw['updatedAt'] ?? runMetadata['finished_at'] ?? createdAt);
    const events = Array.isArray(raw['events']) ? raw['events'].map((event) => this.normalizeTaskEvent(event)) : [];
    return {
      id: String(raw['id'] ?? runId ?? randomUUID()),
      title: String(raw['title'] ?? this.titleFromPrompt(String(raw['prompt'] ?? raw['summary'] ?? 'Runtime task'))),
      summary: String(raw['summary'] ?? raw['prompt'] ?? ''),
      status,
      label: this.stringValue(raw['label']) || (isPlannedTask ? 'planned-task' : undefined),
      date: this.displayDate(updatedAt),
      tokens: this.taskTokens(sessionId, runId),
      plan: String(raw['plan'] ?? ''),
      owner: String(raw['owner'] ?? raw['agent_id'] ?? raw['agentId'] ?? 'unassigned'),
      agentId: String(raw['agent_id'] ?? raw['agentId'] ?? 'unassigned'),
      duration: this.durationText(runMetadata['duration_seconds']),
      prompt: String(raw['prompt'] ?? ''),
      messageId: this.stringValue(raw['message_id'] ?? raw['messageId']) || undefined,
      messagePath: this.stringValue(raw['message_path'] ?? raw['messagePath']) ? this.relativePath(String(raw['message_path'] ?? raw['messagePath'])) : undefined,
      runId: runId || undefined,
      sessionId: sessionId || undefined,
      createdAt,
      updatedAt,
      events,
      source: String(raw['source'] ?? (isPlannedTask ? 'planned-task' : 'controller')),
      planId: this.stringValue(raw['plan_id'] ?? raw['planId']) || undefined,
      planTitle: this.stringValue(raw['plan_title'] ?? raw['planTitle']) || undefined,
      plannedTaskId: this.stringValue(raw['planned_task_id'] ?? raw['plannedTaskId']) || undefined,
      taskPath: this.stringValue(raw['task_path'] ?? raw['taskPath']) ? this.relativePath(String(raw['task_path'] ?? raw['taskPath'])) : undefined,
      tasksYamlPath: this.stringValue(raw['tasks_yaml_path'] ?? raw['tasksYamlPath']) ? this.relativePath(String(raw['tasks_yaml_path'] ?? raw['tasksYamlPath'])) : undefined,
      description: this.stringValue(raw['description']) || undefined,
      files: asStringArray(raw['files']),
      dependsOn: asStringArray(raw['depends_on'] ?? raw['dependsOn']),
      acceptanceCriteria: asStringArray(raw['acceptance_criteria'] ?? raw['acceptanceCriteria']),
    };
  }

  private normalizeTaskEvent(value: unknown): TaskEvent {
    const event = asRecord(value);
    return {
      ts: String(event['ts'] ?? event['event_at'] ?? this.now()),
      type: String(event['type'] ?? event['event'] ?? 'task.event'),
      status: typeof event['status'] === 'string' ? event['status'] : undefined,
      message: String(event['message'] ?? event['detail'] ?? ''),
      details: asRecord(event['details']),
    };
  }

  private async plannedTasks(linkedTasks: Set<string>): Promise<TaskRecord[]> {
    const paths = await this.findFiles(this.plannedTasksRoot, (path) => basename(path) === 'tasks.yaml');
    const tasks: TaskRecord[] = [];
    for (const path of paths) {
      const manifest = await this.readYaml(path);
      const plan = asRecord(manifest['plan']);
      const planId = String(plan['id'] ?? basename(dirname(path)));
      const planTitle = String(plan['title'] ?? planId);
      const entries = Array.isArray(manifest['tasks']) ? manifest['tasks'] : [];
      for (const entry of entries) {
        const rawTask = asRecord(entry);
        const plannedTaskId = String(rawTask['id'] ?? rawTask['name'] ?? '');
        if (!plannedTaskId || linkedTasks.has(`${planId}:${plannedTaskId}`)) continue;
        const markdown = String(rawTask['markdown'] ?? `${plannedTaskId}.md`);
        const taskPath = resolve(dirname(path), markdown);
        const description = String(rawTask['description'] ?? '');
        const prompt = [
          `Plan: ${planTitle}`,
          `Task: ${String(rawTask['title'] ?? plannedTaskId)}`,
          '',
          description,
        ].join('\n');
        tasks.push(await this.normalizeTask({
          id: `planned-${planId}-${plannedTaskId}`,
          title: rawTask['title'],
          summary: description,
          status: rawTask['status'],
          owner: 'unassigned',
          agent_id: 'unassigned',
          prompt,
          plan: this.relativePath(path),
          created_at: rawTask['created_at'] ?? plan['created_at'],
          updated_at: rawTask['updated_at'] ?? plan['updated_at'],
          events: rawTask['events'],
          source: 'planned-task',
          label: 'planned-task',
          plan_id: planId,
          plan_title: planTitle,
          planned_task_id: plannedTaskId,
          task_path: taskPath,
          tasks_yaml_path: path,
          description,
          files: rawTask['files'],
          depends_on: rawTask['depends_on'],
          acceptance_criteria: rawTask['acceptance_criteria'],
        }));
      }
    }
    return tasks;
  }

  private async tasksFromRuns(knownRunIds: Set<string>): Promise<TaskRecord[]> {
    const runJsonPaths = await this.findFiles(resolve(this.stateRoot, 'logs'), (path) => basename(path) === 'run.json');
    const tasks: TaskRecord[] = [];
    for (const path of runJsonPaths) {
      const raw = await this.readJson(path);
      const runId = String(raw['run_id'] ?? '');
      if (!runId || knownRunIds.has(runId)) continue;
      const sessionId = String(raw['session_id'] ?? '');
      const events = await this.readJsonl(resolve(dirname(path), 'events.jsonl'), 50);
      const started = this.oldestMatchingEvent(events, 'run.started');
      const prompt = String(started['message'] ?? 'Runtime run');
      const task = await this.normalizeTask({
        id: runId,
        title: this.titleFromPrompt(prompt),
        summary: prompt,
        prompt,
        status: raw['status'],
        agent_id: Array.isArray(raw['agent_ids']) ? raw['agent_ids'][0] : 'runtime',
        run_id: runId,
        session_id: sessionId,
        created_at: raw['started_at'],
        updated_at: raw['finished_at'] ?? raw['started_at'],
        events: events.reverse().slice(0, 12).map((event) => ({
          ts: event['ts'],
          type: event['type'],
          status: event['status'],
          message: String(event['message'] ?? ''),
        })),
      });
      tasks.push(task);
    }
    return tasks;
  }

  private async runtimeWorkLogs(): Promise<WorkLog[]> {
    const eventPaths = await this.findFiles(resolve(this.stateRoot, 'logs'), (path) => basename(path) === 'events.jsonl');
    const logs: WorkLog[] = [];
    for (const path of eventPaths) {
      const events = await this.readJsonl(path, 80);
      for (const event of events) {
        const type = String(event['type'] ?? '');
        if (!type || (!type.includes('failed') && !type.includes('completed') && type !== 'run.started' && type !== 'error')) continue;
        logs.push({
          id: `${String(event['run_id'] ?? basename(dirname(path)))}-${String(event['seq'] ?? logs.length)}`,
          date: this.displayDate(String(event['ts'] ?? '')),
          event: type,
          agent: String(event['agent_id'] ?? 'runtime'),
          detail: String(event['message'] ?? asRecord(event['payload'])['exception'] ?? type),
          status: typeof event['status'] === 'string' ? event['status'] : undefined,
          path: this.relativePath(path),
        });
      }
    }
    return logs.slice(0, MAX_ITEMS);
  }

  private async workflowRunCounts(): Promise<Map<string, number>> {
    const counts = new Map<string, number>();
    const eventPaths = await this.findFiles(resolve(this.stateRoot, 'logs'), (path) => basename(path) === 'events.jsonl');
    for (const path of eventPaths) {
      const events = await this.readJsonl(path, 200);
      const resolver = events.find((event) => event['type'] === 'resolver.completed');
      const workflowId = String(asRecord(resolver?.['payload'])['workflow_id'] ?? '');
      if (workflowId) counts.set(workflowId, (counts.get(workflowId) ?? 0) + 1);
    }
    return counts;
  }

  private async runStatsByAgent(): Promise<Map<string, { runs: number; completed: number }>> {
    const stats = new Map<string, { runs: number; completed: number }>();
    const runJsonPaths = await this.findFiles(resolve(this.stateRoot, 'logs'), (path) => basename(path) === 'run.json');
    for (const path of runJsonPaths) {
      const raw = await this.readJson(path);
      const ids = Array.isArray(raw['agent_ids']) ? raw['agent_ids'].filter((item): item is string => typeof item === 'string') : [];
      for (const id of ids) {
        const current = stats.get(id) ?? { runs: 0, completed: 0 };
        current.runs += 1;
        if (raw['status'] === 'completed') current.completed += 1;
        stats.set(id, current);
      }
    }
    return stats;
  }

  private async agentHistory(agentId: string): Promise<string[]> {
    const records = await this.messageRecords();
    return records
      .filter((record) => record.sender === agentId || record.recipient === agentId)
      .slice(0, 5)
      .map((record) => `${record.status}: ${record.type} ${record.sender} -> ${record.recipient}`);
  }

  private async runMetadata(sessionId: string | null, runId: string | null): Promise<Record<string, unknown>> {
    if (!sessionId || !runId) return {};
    const path = resolve(this.stateRoot, 'logs', sessionId, runId, 'run.json');
    if (!existsSync(path)) return {};
    return this.readJson(path);
  }

  private taskTokens(sessionId: string | null, runId: string | null): number {
    if (!sessionId || !runId) return 0;
    const path = resolve(this.stateRoot, 'logs', sessionId, runId, 'metrics.json');
    if (!existsSync(path)) return 0;
    return 0;
  }

  private taskStatus(value: string): TaskStatus {
    if (value === 'completed') return 'complete';
    if (value === 'failed' || value === 'cancelled') return 'need rework';
    if (value === 'implementing' || value === 'complete' || value === 'need rework' || value === 'awaiting implementation') return value;
    return 'awaiting implementation';
  }

  private async ensureMessagingRoot(): Promise<void> {
    const directories = [
      resolve(this.messageRoot, 'inbox'),
      resolve(this.messageRoot, 'processed'),
      resolve(this.messageRoot, 'failed'),
      resolve(this.messageRoot, 'records', 'messages'),
      resolve(this.messageRoot, 'records', 'tasks'),
      resolve(this.messageRoot, 'errors'),
      resolve(this.messageRoot, 'debug-sessions'),
    ];
    for (const directory of directories) await mkdir(directory, { recursive: true });
    const eventLog = resolve(this.messageRoot, 'records', 'events.jsonl');
    if (!existsSync(eventLog)) await writeFile(eventLog, '', 'utf-8');
    const manifest = {
      version: 1,
      root: this.messageRoot,
      purpose: 'Durable transparent agent messaging, task assignment, and UI debug artifacts.',
      directories: {
        inbox: 'Pending messages grouped by recipient agent id.',
        processed: 'Messages moved here after a handler or worker accepts them.',
        failed: 'Messages moved here with sibling .error.txt files when processing fails.',
        'records/messages': 'Current lifecycle record for every known message, including payload.',
        'records/tasks': 'Controller-created task records linked to task_request messages and runtime runs.',
        'current-error.json': 'Current unresolved operational error alert, when one exists.',
        errors: 'Archived fixed, superseded, and historical operational error alerts.',
        'debug-sessions': 'Selenium UI debugger manifests, screenshots, console logs, and network errors.',
      },
      event_log: eventLog,
      message_record_fields: [
        'id',
        'created_at',
        'updated_at',
        'sender',
        'recipient',
        'type',
        'reply_to',
        'status',
        'path',
        'folder_agent_id',
        'payload',
        'error',
      ],
      task_statuses: ['awaiting implementation', 'implementing', 'complete', 'need rework'],
      error_statuses: ['active', 'superseded', 'fixed'],
    };
    await this.writeJsonAtomic(resolve(this.messageRoot, 'manifest.json'), manifest);
  }

  private async findFiles(root: string, accept: (path: string) => boolean): Promise<string[]> {
    if (!existsSync(root)) return [];
    const found: string[] = [];
    const entries = await readdir(root, { withFileTypes: true }).catch(() => []);
    for (const entry of entries) {
      const path = resolve(root, entry.name);
      if (entry.isDirectory()) {
        found.push(...(await this.findFiles(path, accept)));
      } else if (entry.isFile() && accept(path)) {
        found.push(path);
      }
    }
    return found;
  }

  private async writeJsonAtomic(path: string, value: unknown): Promise<void> {
    await mkdir(dirname(path), { recursive: true });
    const temporary = `${path}.${randomUUID()}.tmp`;
    await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf-8');
    await rename(temporary, path);
  }

  private safeIdentifier(value: unknown, label: string): string {
    const id = String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    if (!IDENTIFIER.test(id)) throw new BadRequestException(`Invalid ${label}`);
    return id;
  }

  private stringValue(value: unknown): string | null {
    return typeof value === 'string' && value ? value : null;
  }

  private titleFromPrompt(prompt: string): string {
    const firstLine = prompt.split('\n').find((line) => line.trim()) ?? 'Runtime task';
    return firstLine.length > 80 ? `${firstLine.slice(0, 77)}...` : firstLine;
  }

  private summaryFromPrompt(prompt: string): string {
    const compact = prompt.replace(/\s+/g, ' ').trim();
    return compact.length > 220 ? `${compact.slice(0, 217)}...` : compact;
  }

  private firstMeaningfulLine(content: string): string {
    const line = content.split('\n').find((item) => item.trim() && !item.trim().startsWith('#'));
    return line?.trim() ?? '';
  }

  private markdownTitle(content: string): string {
    const title = content.split('\n').find((line) => line.startsWith('# '));
    return title ? title.replace(/^#\s+/, '').trim() : '';
  }

  private firstParagraph(content: string): string {
    const paragraph = content
      .split('\n')
      .map((line) => line.trim())
      .find((line) => line && !line.startsWith('#') && !line.startsWith('---'));
    return paragraph ?? 'No summary available.';
  }

  private durationText(value: unknown): string {
    if (typeof value !== 'number') return 'pending';
    if (value < 60) return `${value.toFixed(1)}s`;
    return `${Math.round(value / 60)}m`;
  }

  private displayDate(value: string): string {
    if (!value) return '';
    return value.replace('T', ' ').replace('Z', '').slice(0, 19);
  }

  private relativePath(path: string): string {
    const resolved = resolve(path);
    return resolved.startsWith(this.root) ? relative(this.root, resolved) : path;
  }

  private absolutePath(path: string): string {
    return resolve(path.startsWith(this.root) ? path : safeJoin(this.root, path));
  }

  private messageEventDetail(event: Record<string, unknown>): string {
    const sender = String(event['sender'] ?? '');
    const recipient = String(event['recipient'] ?? event['agent_id'] ?? '');
    const messageType = String(event['message_type'] ?? event['status'] ?? '');
    const taskId = String(event['task_id'] ?? '');
    if (taskId) return `${taskId} ${messageType}`.trim();
    return `${sender} -> ${recipient} ${messageType}`.trim();
  }

  private now(): string {
    return new Date().toISOString();
  }

  private oldestMatchingEvent(events: Record<string, unknown>[], type: string): Record<string, unknown> {
    for (const event of [...events].reverse()) {
      if (event['type'] === type) return event;
    }
    return {};
  }
}
