import { CommonModule } from '@angular/common';
import { Component, input, signal } from '@angular/core';
import { Task } from '../../shared-services/interfaces';
@Component({ selector:'app-task-detail', standalone:true, imports:[CommonModule], templateUrl:'./task-detail.component.html', styleUrl:'./task-detail.component.css' })
export class TaskDetailComponent { readonly task = input.required<Task>(); readonly editing = signal(false); readonly plan = signal(''); constructor(){ } toggleEdit(): void { this.editing.update((value) => !value); } setPlan(value: string): void { this.plan.set(value); } }
