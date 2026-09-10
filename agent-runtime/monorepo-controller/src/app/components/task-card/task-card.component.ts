import { CommonModule } from '@angular/common';
import { Component, input, output } from '@angular/core';
import { Task } from '../../shared-services/interfaces';
@Component({ selector:'app-task-card', standalone:true, imports:[CommonModule], templateUrl:'./task-card.component.html', styleUrl:'./task-card.component.css' })
export class TaskCardComponent { readonly task = input.required<Task>(); readonly selected = input(false); readonly taskSelected = output<string>(); }
