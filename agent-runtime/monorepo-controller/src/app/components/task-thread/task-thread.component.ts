import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { StoreService } from '../../shared-services/store.service';
import { MessageRecord, Task } from '../../shared-services/interfaces';
import { TaskCardComponent } from '../task-card/task-card.component';

@Component({ selector:'app-task-thread', standalone:true, imports:[CommonModule,FormsModule,TaskCardComponent], templateUrl:'./task-thread.component.html', styleUrl:'./task-thread.component.css' })
export class TaskThreadComponent implements OnInit {
  readonly store = inject(StoreService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly activeTab = signal<'thread'|'new'|'generated'>('thread');
  readonly newTitle = signal('');
  readonly newPrompt = signal('');
  readonly selected = computed(() => this.store.tasks().find((task) => task.id === this.store.selectedTaskId()) ?? this.store.tasks()[0] ?? null);
  readonly openTasks = computed(() => this.store.tasks().filter((task) => task.status !== 'complete'));
  readonly completedTasks = computed(() => this.store.tasks().filter((task) => task.status === 'complete'));
  readonly userCreatedTasks = computed(() => this.store.tasks().filter((task) => task.source === 'controller' || Boolean(task.messageId)));

  ngOnInit(): void {
    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (id) this.store.selectTask(id);
    });
  }

  choose(id: string): void {
    this.store.selectTask(id);
    this.router.navigate(['/task-thread', id]);
  }

  isSelected(id: string): boolean {
    return this.selected()?.id === id;
  }

  createTask(): void {
    const prompt = this.newPrompt().trim();
    if (!prompt) return;
    this.store.createTask({ title: this.newTitle().trim() || undefined, prompt }).subscribe((task) => {
      if (!task) return;
      this.newTitle.set('');
      this.newPrompt.set('');
      this.choose(task.id);
      this.activeTab.set('thread');
    });
  }

  startTask(task: Task): void {
    this.store.startTask(task.id).subscribe();
  }

  canStart(task: Task): boolean {
    return Boolean(task.messageId) && task.status === 'awaiting implementation' && this.relatedMessages(task).some((message) => message.status === 'pending');
  }

  relatedMessages(task: Task): MessageRecord[] {
    const messages = this.store.messaging()?.messages ?? [];
    return messages.filter((message) => message.id === task.messageId || message.reply_to === task.messageId);
  }

  eventDetail(event: Record<string, unknown> | undefined): string {
    if (!event) return '';
    return JSON.stringify(event, null, 2);
  }
}
