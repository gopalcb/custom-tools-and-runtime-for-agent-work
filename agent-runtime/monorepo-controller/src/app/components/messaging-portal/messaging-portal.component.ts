import { CommonModule } from '@angular/common';
import { Component, signal } from '@angular/core';

type PortalTab = 'overview' | 'channels' | 'queue' | 'audit';

@Component({
  selector: 'app-messaging-portal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './messaging-portal.component.html',
  styleUrl: './messaging-portal.component.css'
})
export class MessagingPortalComponent {
  readonly activeTab = signal<PortalTab>('overview');
}
