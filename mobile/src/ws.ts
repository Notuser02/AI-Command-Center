// WebSocket manager with auto-reconnect — one connection for the whole app.
//
// The backend broadcasts structured events from WS /ws (see
// services/connection_manager.py): task_created, task_deleted,
// task_status_changed, task_message, task_token (live stream chunks),
// task_log, approval_required, approval_resolved.

import type { WsEvent } from './types';

type Handler = (event: WsEvent) => void;
export type WsStatus = 'disconnected' | 'connecting' | 'connected';

class WSManager {
  private ws: WebSocket | null = null;
  private url: string | null = null;
  private handlers = new Set<Handler>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUs = false;

  status: WsStatus = 'disconnected';
  onStatusChange: ((status: WsStatus) => void) | null = null;

  connect(url: string) {
    if (this.url === url && this.status === 'connected') return;
    this.url = url;
    this.disconnect(); // drop any previous connection first
    this.closedByUs = false;
    this.setStatus('connecting');

    try {
      this.ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => this.setStatus('connected');

    this.ws.onmessage = (raw) => {
      try {
        const msg = JSON.parse(String(raw.data)) as WsEvent;
        this.handlers.forEach((h) => h(msg));
      } catch {
        // ignore malformed frames
      }
    };

    this.ws.onclose = () => {
      this.setStatus('disconnected');
      if (!this.closedByUs) this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose fires after onerror; reconnect handled there
    };
  }

  disconnect() {
    this.closedByUs = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this.setStatus('disconnected');
  }

  subscribe(handler: Handler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  private scheduleReconnect() {
    if (this.reconnectTimer || this.closedByUs) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.url && !this.closedByUs) this.connect(this.url);
    }, 3000);
  }

  private setStatus(s: WsStatus) {
    this.status = s;
    this.onStatusChange?.(s);
  }
}

export const wsManager = new WSManager();
