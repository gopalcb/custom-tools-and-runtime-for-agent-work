import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { StoreService } from '../../shared-services/store.service';
import { MessageRecord } from '../../shared-services/interfaces';

type PortalTab = 'overview' | 'messages' | 'unresolved' | 'errors' | 'queue' | 'debug';

@Component({
  selector: 'app-messaging-portal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './messaging-portal.component.html',
  styleUrl: './messaging-portal.component.css'
})
export class MessagingPortalComponent {
  readonly store = inject(StoreService);
  readonly activeTab = signal<PortalTab>('overview');
  readonly recipient = signal('agent-ui-debugger');
  readonly messageType = signal('ui_debug_request');
  readonly payload = signal('{\n  "url": "http://localhost:1001",\n  "request_id": "controller-ui"\n}');
  readonly debugUrl = signal('http://localhost:1001');
  readonly selectedMessageId = signal('');
  readonly pendingMessages = computed(() => (this.store.messaging()?.messages ?? []).filter((message) => message.status === 'pending'));
  readonly unresolvedMessages = computed(() => this.pendingMessages());
  readonly failedMessages = computed(() => (this.store.messaging()?.messages ?? []).filter((message) => message.status === 'failed'));
  readonly trackedErrors = computed(() => this.store.messaging()?.errors ?? []);
  readonly currentError = computed(() => this.store.messaging()?.summary?.currentError ?? null);
  readonly selectedMessage = computed(() => {
    const messages = this.store.messaging()?.messages ?? [];
    return messages.find((message) => message.id === this.selectedMessageId()) ?? messages[0] ?? null;
  });

  selectMessage(message: MessageRecord): void {
    this.selectedMessageId.set(message.id);
  }

  format(value: unknown): string {
    return JSON.stringify(value ?? {}, null, 2);
  }

  sendMessage(): void {
    const recipient = this.recipient().trim();
    const type = this.messageType().trim();
    if (!recipient || !type) return;
    this.store.sendMessage({ recipient, type, payload: this.parsePayload() }).subscribe();
  }

  sendDebugRequest(): void {
    const url = this.debugUrl().trim();
    if (!url) return;
    this.store.sendMessage({
      recipient: 'agent-ui-debugger',
      type: 'ui_debug_request',
      payload: { url, request_id: `ui-debug-${Date.now()}`, wait_seconds: 1, full_page_screenshot: true },
    }).subscribe();
    this.activeTab.set('messages');
  }

  private parsePayload(): Record<string, unknown> {
    try {
      const value = JSON.parse(this.payload()) as unknown;
      return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
    } catch {
      return {};
    }
  }
}
