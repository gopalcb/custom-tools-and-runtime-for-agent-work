import { Routes } from '@angular/router';
import { TaskThreadComponent } from './components/task-thread/task-thread.component';
import { AgentsViewComponent } from './components/agents-view/agents-view.component';
import { SkillsViewComponent } from './components/skills-view/skills-view.component';
import { WorkflowsViewComponent } from './components/workflows-view/workflows-view.component';
import { MemoryViewComponent } from './components/memory-view/memory-view.component';
import { WorkLogsViewComponent } from './components/work-logs-view/work-logs-view.component';
import { MessagingPortalComponent } from './components/messaging-portal/messaging-portal.component';
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'task-thread' },
  { path: 'task-thread', component: TaskThreadComponent },
  { path: 'task-thread/:id', component: TaskThreadComponent },
  { path: 'agents', component: AgentsViewComponent },
  { path: 'skills', component: SkillsViewComponent },
  { path: 'workflows', component: WorkflowsViewComponent },
  { path: 'memory', component: MemoryViewComponent },
  { path: 'work-logs', component: WorkLogsViewComponent },
  { path: 'messaging', component: MessagingPortalComponent },
  { path: '**', redirectTo: 'task-thread' }
];
