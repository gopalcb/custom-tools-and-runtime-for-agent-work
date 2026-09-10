import { Component, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CodexRealtimeService } from '../../shared-services/codex-realtime.service';

type StepState = 'queued' | 'running' | 'completed' | 'failed';
type WorkflowStep = { id: string; title: string; state: StepState };
type Activity = { time: string; text: string; tone: 'default' | 'accent' | 'success' | 'warning' };
type BackgroundTask = { id: string; title: string; detail: string; state: 'running' | 'complete' | 'failed' };

const WORKFLOW_STEPS: WorkflowStep[] = [
  { id: 'understand', title: 'Understand request', state: 'queued' },
  { id: 'context', title: 'Load project context', state: 'queued' },
  { id: 'plan', title: 'Plan implementation', state: 'queued' },
  { id: 'execute', title: 'Apply changes', state: 'queued' },
  { id: 'validate', title: 'Validate results', state: 'queued' },
  { id: 'complete', title: 'Complete turn', state: 'queued' },
];

@Component({
  selector: 'app-agent-client',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './agent-client.component.html',
  styleUrl: './agent-client.component.css',
})
export class AgentClientComponent {
  private readonly codex = inject(CodexRealtimeService);

  readonly prompt = signal('');
  readonly turnId = signal<string | null>(null);
  readonly active = signal(false);
  readonly workflow = signal<WorkflowStep[]>(this.newWorkflow());
  readonly activities = signal<Activity[]>([]);
  readonly backgroundTasks = signal<BackgroundTask[]>([]);
  readonly connected = this.codex.connected;

  constructor() {
    effect(() => {
      const latest = this.codex.events().at(-1);
      if (!latest || latest.turnId !== this.turnId()) return;
      this.consumeEvent(latest.event);
    });
    effect(() => {
      if (this.codex.completedTurnId() !== this.turnId() || !this.active()) return;
      this.active.set(false);
      this.workflow.update((steps) => steps.map((step) => ({ ...step, state: 'completed' })));
      this.log('Turn completed.', 'success');
    });
  }

  submit(): void {
    const prompt = this.prompt().trim();
    if (!prompt || this.active()) return;

    if (prompt === '/clear' || prompt === '/new') {
      this.reset();
      return;
    }

    this.prompt.set('');
    this.active.set(true);
    this.workflow.set(this.newWorkflow('understand'));
    this.backgroundTasks.set([]);
    this.activities.set([{ time: this.time(), text: `› ${prompt}`, tone: 'accent' }]);
    this.log('Starting a Codex turn…', 'default');
    this.codex.startTurn({ prompt, sandbox: 'workspace_write', ephemeral: false }).subscribe({
      next: (turn) => {
        this.turnId.set(turn.turn_id);
        this.log(`Connected to turn ${turn.turn_id}`, 'accent');
        this.codex.subscribe(turn.turn_id);
      },
      error: (error: unknown) => {
        this.active.set(false);
        this.markCurrentStep('failed');
        this.log(this.errorText(error), 'warning');
      },
    });
  }

  interrupt(): void {
    const turnId = this.turnId();
    if (!turnId || !this.active()) return;
    this.codex.interrupt(turnId).subscribe({
      next: () => this.log('Interrupt requested.', 'warning'),
      error: (error: unknown) => this.log(this.errorText(error), 'warning'),
    });
  }

  handleEnter(event: Event): void {
    if ((event as KeyboardEvent).shiftKey) return;
    event.preventDefault();
    this.submit();
  }

  completedSteps(): number {
    return this.workflow().filter((step) => step.state === 'completed').length;
  }

  progress(): number {
    return Math.round((this.completedSteps() / this.workflow().length) * 100);
  }

  private consumeEvent(event: Record<string, unknown>): void {
    const type = this.eventType(event);
    const message = this.eventMessage(event);
    const lower = `${type} ${message}`.toLowerCase();
    const isFailure = lower.includes('error') || lower.includes('failed');
    const isComplete = lower.includes('completed') || lower.includes('complete') || lower.includes('finished');

    this.advanceWorkflow(lower, isFailure, isComplete);
    this.trackTool(event, lower, message, isFailure, isComplete);
    if (message) this.log(message, isFailure ? 'warning' : isComplete ? 'success' : 'default');

    if (lower.includes('turn.completed') || lower.includes('turn/complete') || lower.includes('turn.failed') || lower.includes('turn/failed')) {
      this.active.set(false);
      if (isFailure) this.markCurrentStep('failed');
      else this.workflow.update((steps) => steps.map((step) => ({ ...step, state: 'completed' })));
    }
  }

  private advanceWorkflow(text: string, failed: boolean, complete: boolean): void {
    const match = [
      ['context', 'context'], ['file', 'context'], ['plan', 'plan'], ['reason', 'plan'],
      ['tool', 'execute'], ['command', 'execute'], ['edit', 'execute'], ['write', 'execute'],
      ['test', 'validate'], ['validat', 'validate'], ['complete', 'complete'], ['finish', 'complete'],
    ].find(([token]) => text.includes(token));
    if (!match) return;
    const stepId = match[1];
    this.workflow.update((steps) => steps.map((step, index) => {
      const targetIndex = steps.findIndex((item) => item.id === stepId);
      if (step.id === stepId) return { ...step, state: failed ? 'failed' : complete ? 'completed' : 'running' };
      if (index < targetIndex && step.state === 'queued') return { ...step, state: 'completed' };
      return step;
    }));
  }

  private trackTool(event: Record<string, unknown>, text: string, message: string, failed: boolean, complete: boolean): void {
    if (!text.includes('tool') && !text.includes('command')) return;
    const params = this.record(event['params']);
    const id = this.stringValue(event['item_id']) || this.stringValue(params?.['id']) || `${this.backgroundTasks().length + 1}`;
    const title = this.stringValue(params?.['name']) || this.stringValue(event['name']) || 'Codex tool';
    const detail = message || this.stringValue(params?.['command']) || 'Working…';
    const state: BackgroundTask['state'] = failed ? 'failed' : complete ? 'complete' : 'running';
    this.backgroundTasks.update((tasks) => {
      const existing = tasks.findIndex((task) => task.id === id);
      const task = { id, title, detail, state };
      return existing < 0 ? [...tasks, task] : tasks.map((item, index) => index === existing ? task : item);
    });
  }

  private markCurrentStep(state: StepState): void {
    this.workflow.update((steps) => {
      const current = steps.findIndex((step) => step.state === 'running');
      return steps.map((step, index) => index === (current < 0 ? 0 : current) ? { ...step, state } : step);
    });
  }

  private newWorkflow(running?: string): WorkflowStep[] {
    return WORKFLOW_STEPS.map((step) => ({ ...step, state: step.id === running ? 'running' : 'queued' }));
  }

  private eventType(event: Record<string, unknown>): string {
    return this.stringValue(event['type']) || this.stringValue(event['method']) || 'codex.event';
  }

  private eventMessage(event: Record<string, unknown>): string {
    const params = this.record(event['params']);
    return this.stringValue(event['message']) || this.stringValue(params?.['message']) || this.stringValue(params?.['delta']) || this.stringValue(params?.['text']) || this.eventType(event);
  }

  private record(value: unknown): Record<string, unknown> | null {
    return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
  }

  private stringValue(value: unknown): string | null {
    return typeof value === 'string' && value.trim() ? value.trim() : null;
  }

  private log(text: string, tone: Activity['tone']): void {
    this.activities.update((items) => [...items.slice(-199), { time: this.time(), text, tone }]);
  }

  private reset(): void {
    this.prompt.set('');
    this.turnId.set(null);
    this.active.set(false);
    this.workflow.set(this.newWorkflow());
    this.activities.set([]);
    this.backgroundTasks.set([]);
  }

  private time(): string {
    return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date());
  }

  private errorText(error: unknown): string {
    return error instanceof Error ? `Unable to reach Codex: ${error.message}` : 'Unable to reach Codex.';
  }
}
