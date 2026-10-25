// Thin HTTP client over the EXISTING backend endpoints — nothing new on the server.

import type { Approval, ModelsResponse, Task } from './types';

// The phone must reach the PC over the network — never 'localhost', which
// would mean the phone itself. This is only a FIRST-RUN default; each user
// sets their own PC address (LAN IP or Tailscale 100.x) in the Settings
// screen, which persists. The web app served by the backend at /m ignores
// this entirely and auto-detects its server.
export const DEFAULT_SERVER_URL = 'http://192.168.1.100:8000';

let baseUrl = DEFAULT_SERVER_URL;

export function setBaseUrl(url: string) {
  baseUrl = (url || '').trim().replace(/\/+$/, '');
}

export function getBaseUrl() {
  return baseUrl;
}

export function wsUrl() {
  return baseUrl.replace(/^http/, 'ws') + '/ws';
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(baseUrl + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({} as any));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // GET /status — health check / connection test
  getStatus: (timeoutMs = 5000) =>
    Promise.race([
      request<{ status: string }>('/status'),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Connection timed out')), timeoutMs)),
    ]),

  getModels: () => request<ModelsResponse>('/models'),

  listTasks: (limit = 50) => request<Task[]>(`/tasks?limit=${limit}`),
  getTask: (id: number) => request<Task>(`/tasks/${id}`),
  createTask: (body: { name?: string | null; task: string; provider: string; model?: string }) =>
    request<Task>('/tasks', { method: 'POST', body: JSON.stringify(body) }),
  sendMessage: (id: number, message: string) =>
    request<Task>(`/tasks/${id}/messages`, { method: 'POST', body: JSON.stringify({ message }) }),
  stopTask: (id: number) => request<Task>(`/tasks/${id}/stop`, { method: 'POST' }),
  completeTask: (id: number) => request<Task>(`/tasks/${id}/complete`, { method: 'POST' }),
  deleteTask: (id: number) => request<{ deleted: boolean; id: number }>(`/tasks/${id}`, { method: 'DELETE' }),

  getPendingApprovals: () => request<Approval[]>('/approvals/pending'),
  resolveApproval: (id: number, approve: boolean) =>
    request<Approval>(`/approvals/${id}/${approve ? 'approve' : 'deny'}`, { method: 'POST' }),

  // ── Online provider ("bring your own API key") ──
  getOnlineConfig: () =>
    request<{ base_url: string; api_key_set: boolean; default_model: string }>('/online/config'),
  saveOnlineConfig: (body: { base_url?: string; api_key?: string; default_model?: string }) =>
    request<{ ok?: boolean; base_url: string; api_key_set: boolean; models?: string[] }>(
      '/online/config', { method: 'POST', body: JSON.stringify(body) }),
  getOnlineModels: () =>
    request<{ models: string[]; error: string | null }>('/online/models'),
};
