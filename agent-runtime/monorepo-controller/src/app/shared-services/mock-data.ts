import { Agent, MemoryEntry, Skill, Task, Workflow, WorkLog } from './interfaces';

export const mockTasks: Task[] = [
  { id: 'task-ui', title: 'Build Monorepo Controller UI', summary: 'Create the responsive controller shell with routed runtime views and mock data.', status: 'implementing', date: 'In progress', tokens: 12480, duration: 'active', owner: 'ui-orchestrator', plan: '# Implementation plan\n\n- Establish the **controller shell** and visual tokens.\n- Keep the agent chat persistent while routing the workspace.\n- Add mock-backed task, agent, skill, workflow, memory, and log views.\n- Validate the SPA with a production build.' },
  { id: 'task-runtime', title: 'Thin runtime facade', summary: 'Keep resolution and workflow state inside the shared agent runtime.', status: 'complete', date: 'Sep 08, 2026', tokens: 8920, duration: '18 min', owner: 'runtime-architect', plan: '# Implementation plan\n\n- Move execution concerns into the shared runtime.\n- Preserve the gateway as a thin facade.\n- Emit RuntimeEvent facts for the console.' },
  { id: 'task-events', title: 'Live RuntimeEvent stream', summary: 'Persist and present runtime facts for live console state.', status: 'complete', date: 'Sep 06, 2026', tokens: 6140, duration: '11 min', owner: 'event-stream-agent', plan: '# Implementation plan\n\n- Define the event contract.\n- Connect workflow transitions to persisted facts.\n- Provide a stable consumer surface.' }
];

export const mockAgents: Agent[] = [
  { id: 'runtime-architect', name: 'Runtime Architect', role: 'Architecture & execution', status: 'available', summary: 'Owns the shared runtime boundaries, resolution, and execution lifecycle.', skills: ['context-standard', 'context-deep', 'python-coder'], history: ['Thin facade review completed', 'Runtime boundaries documented', 'Workflow state migration shipped'], performance: [{ label: 'Tasks completed', value: '24' }, { label: 'Avg. tokens', value: '7.8k' }, { label: 'Reliability', value: '98%' }] },
  { id: 'ui-orchestrator', name: 'UI Orchestrator', role: 'Frontend experience', status: 'implementing', summary: 'Builds focused operator surfaces for agent runtime visibility.', skills: ['angular-ui', 'context-standard', 'testing'], history: ['Controller shell started', 'Task thread patterns defined'], performance: [{ label: 'Tasks completed', value: '12' }, { label: 'Avg. tokens', value: '9.2k' }, { label: 'Reliability', value: '96%' }] },
  { id: 'event-stream-agent', name: 'Event Stream Agent', role: 'Events & observability', status: 'available', summary: 'Turns runtime transitions into durable, useful console facts.', skills: ['runtime-events', 'python-coder', 'testing'], history: ['RuntimeEvent schema shipped', 'Work log projection added'], performance: [{ label: 'Tasks completed', value: '18' }, { label: 'Avg. tokens', value: '6.1k' }, { label: 'Reliability', value: '99%' }] }
];

export const mockSkills: Skill[] = [
  { id: 'context-standard', name: 'context-standard', category: 'Repository', summary: 'Efficient retrieval for ordinary engineering tasks.', content: '# context-standard\n\nUse targeted project memory and source retrieval for ordinary repository work.\n\n## Retrieval sequence\n\n1. Read the project summary.\n2. Search matching source and tests.\n3. Stop when the implementation boundary and verification route are known.' },
  { id: 'context-deep', name: 'context-deep', category: 'Investigation', summary: 'Progressive investigation for architecture and difficult incidents.', content: '# context-deep\n\nRetrieve architecture, ADRs, history, and runtime evidence only when each source answers a concrete question.' },
  { id: 'angular-ui', name: 'angular-ui', category: 'Frontend', summary: 'Patterns for maintainable Angular component surfaces.', content: '# angular-ui\n\nPrefer standalone components, route-level composition, signals for local state, and accessible interactive controls.' },
  { id: 'testing', name: 'testing', category: 'Quality', summary: 'Focused checks that protect user-visible behavior.', content: '# testing\n\nValidate the production build, route composition, and interactive state transitions with deterministic fixtures.' },
  { id: 'python-coder', name: 'python-coder', category: 'Engineering', summary: 'Repository conventions for Python changes.', content: '# python-coder\n\nKeep Python projects documented with ARCHITECTURE.md and code-map.yaml and run compile and test checks.' },
  { id: 'runtime-events', name: 'runtime-events', category: 'Runtime', summary: 'Shared event contract for live and persisted facts.', content: '# runtime-events\n\nUse RuntimeEvent for live console state and persisted facts. The console should consume state, not poll JSONL logs.' }
];

export const mockWorkflows: Workflow[] = [
  { name: 'workflow-orchestrator', status: 'active', runs: '48 runs', owner: 'Runtime', description: 'Resolves an agent, executes its workflow, emits events, and finalizes memory.' },
  { name: 'post-completion', status: 'ready', runs: '31 runs', owner: 'Memory', description: 'Captures verified completion facts and makes them available to future work.' },
  { name: 'agent-bootstrap', status: 'ready', runs: '18 runs', owner: 'Registry', description: 'Loads declarative agent definitions and validates project registration.' }
];

export const mockMemory: MemoryEntry[] = [
  { title: 'Runtime boundaries', kind: 'Architecture', updated: '2h ago', excerpt: 'Gateway remains a thin facade; runtime owns resolution, protocol, state, events, and memory.' },
  { title: 'Console event contract', kind: 'Pattern', updated: '1d ago', excerpt: 'RuntimeEvent is the shared source for live UI state and persisted facts.' },
  { title: 'Controller UI direction', kind: 'Decision', updated: '3d ago', excerpt: 'Keep operator chat persistent and change only the right workspace view.' }
];

export const mockWorkLogs: WorkLog[] = [
  { date: 'Today · 10:42', event: 'Task started', agent: 'UI Orchestrator', detail: 'Controller UI implementation moved into the active thread.' },
  { date: 'Today · 09:18', event: 'Workflow completed', agent: 'Runtime Architect', detail: 'Thin runtime facade passed validation.' },
  { date: 'Yesterday · 16:05', event: 'Memory finalized', agent: 'Event Stream Agent', detail: 'RuntimeEvent contract was added to the project memory.' }
];
