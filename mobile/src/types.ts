// Shared types mirroring the backend's Pydantic schemas (models.py).

export type TaskStatus =
  | 'idle'
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface TaskMessage {
  role: string;
  content: string;
  timestamp?: string;
}

export interface Task {
  id: number;
  name: string | null;
  task: string; // the workspace description
  provider: string;
  model: string | null;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  result: string | null;
  logs: any[] | null;
  messages: TaskMessage[] | null;
}

export interface Approval {
  id: number;
  task_id: number;
  tool_name: string;
  arguments: Record<string, any> | null;
  reason: string | null;
  status: string;
  created_at: string;
  resolved_at: string | null;
}

export interface ModelsResponse {
  local: string[];
  online: string[];
  default: { local: string; online: string };
}

// Events arriving over WS /ws — { event: string, data: any }
export interface WsEvent {
  event: string;
  data: any;
}
