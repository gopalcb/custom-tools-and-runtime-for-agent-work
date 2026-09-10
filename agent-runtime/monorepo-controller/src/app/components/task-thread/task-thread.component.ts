import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { StoreService } from '../../shared-services/store.service';
import { Task } from '../../shared-services/interfaces';
import { TaskCardComponent } from '../task-card/task-card.component';

@Component({ selector:'app-task-thread', standalone:true, imports:[CommonModule,TaskCardComponent], templateUrl:'./task-thread.component.html', styleUrl:'./task-thread.component.css' })
export class TaskThreadComponent implements OnInit {
  readonly store = inject(StoreService); private readonly router = inject(Router); private readonly route = inject(ActivatedRoute); readonly selected = signal<Task | null>(null); readonly activeTab = signal<'thread'|'config'|'generated'>('thread');
  ngOnInit(): void { this.route.paramMap.subscribe((params) => { const id = params.get('id') ?? this.store.selectedTaskId(); this.store.selectTask(id); this.selected.set(this.store.tasks().find((task) => task.id === id) ?? null); }); }
  choose(id: string): void { this.store.selectTask(id); this.selected.set(this.store.tasks().find((task) => task.id === id) ?? null); this.router.navigate(['/task-thread', id]); }
}
