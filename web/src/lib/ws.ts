"use client";

export interface WSEvent {
  type: string;
  [key: string]: unknown;
}

type EventHandler = (event: WSEvent) => void;

export class WSManager {
  private ws: WebSocket | null = null;
  private url = "";
  private handlers = new Map<string, Set<EventHandler>>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = false;

  connect(url: string) {
    this.url = url;
    this.shouldReconnect = true;
    this._connect();
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  on(type: string, handler: EventHandler) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(handler);
  }

  off(type: string, handler: EventHandler) {
    this.handlers.get(type)?.delete(handler);
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private _connect() {
    if (!this.url) return;
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (e) => {
        try {
          const event: WSEvent = JSON.parse(e.data as string);
          this.handlers.get(event.type)?.forEach((h) => h(event));
        } catch {
          // ignore malformed frames
        }
      };

      this.ws.onclose = () => {
        if (this.shouldReconnect) {
          this.reconnectTimer = setTimeout(() => this._connect(), 3000);
        }
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      if (this.shouldReconnect) {
        this.reconnectTimer = setTimeout(() => this._connect(), 3000);
      }
    }
  }
}

export const wsManager = new WSManager();
