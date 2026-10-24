// LiveContext: owns the WebSocket connection and keeps live data fresh —
// task list, pending approvals, per-task stream buffers (same pattern as the
// PC dashboard), and a small event feed for the Dashboard screen.
//
// If the WebSocket can't connect, screens still work: a 5s polling loop
// refreshes tasks + approvals whenever wsStatus !== 'connected'.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { api } from '../api';
import { wsManager, type WsStatus } from '../ws';
import type { Approval, Task, WsEvent } from '../types';
import { useSettings } from './SettingsContext';

export interface FeedItem {
  id: number;
  time: string;
  text: string;
  color: string;
}

interface LiveContextValue {
  tasks: Task[];
  approvals: Approval[];
  wsStatus: WsStatus;
  serverReachable: boolean | null;
  streamBuffers: Record<number, string>;
  feed: FeedItem[];
  refreshAll: () => Promise<void>;
  subscribe: (handler: (event: WsEvent) => void) => () => void;
  updateTaskLocal: (task: Task) => void;
}

const LiveContext = createContext<LiveContextValue | null>(null);

let feedCounter = 0;

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const { serverUrl, loaded } = useSettings();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [wsStatus, setWsStatus] = useState<WsStatus>('disconnected');
  const [serverReachable, setServerReachable] = useState<boolean | null>(null);
  const [streamBuffers, setStreamBuffers] = useState<Record<number, string>>({});
  const [feed, setFeed] = useState<FeedItem[]>([]);

  const addFeed = useCallback((text: string, color: string) => {
    feedCounter += 1;
    const item: FeedItem = {
      id: feedCounter,
      time: new Date().toLocaleTimeString(),
      text,
      color,
    };
    setFeed((f) => [item, ...f].slice(0, 30));
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      const [t, a] = await Promise.all([api.listTasks(), api.getPendingApprovals()]);
      setTasks(t);
      setApprovals(a);
      setServerReachable(true);
    } catch {
      setServerReachable(false);
    }
  }, []);

  // ── WebSocket lifecycle: (re)connect whenever the server URL changes ──
  useEffect(() => {
    if (!loaded) return;
    wsManager.onStatusChange = (s) => setWsStatus(s);
    wsManager.connect(serverUrl.replace(/^http/, 'ws') + '/ws');
    refreshAll();
    return () => {
      wsManager.onStatusChange = null;
      wsManager.disconnect();
    };
  }, [loaded, serverUrl, refreshAll]);

  // ── Event handling (single WS subscription shared by the whole app) ──
  useEffect(() => {
    const unsubscribe = wsManager.subscribe((msg: WsEvent) => {
      const { event, data } = msg;
      switch (event) {
        case 'connected':
          addFeed('Real-time stream connected', '#00ff88');
          break;

        case 'task_created':
          addFeed(`Task created: ${data.name || 'TASK-' + data.id}`, '#00f0ff');
          refreshAll();
          break;

        case 'task_deleted':
          setTasks((ts) => ts.filter((t) => t.id !== data.task_id));
          setStreamBuffers((b) => {
            const next = { ...b };
            delete next[data.task_id];
            return next;
          });
          addFeed(`Task #${data.task_id} deleted`, '#ff8800');
          break;

        case 'task_status_changed':
          setTasks((ts) =>
            ts.map((t) => (t.id === data.task_id ? { ...t, status: data.status } : t)),
          );
          if (data.status !== 'running') {
            setStreamBuffers((b) => {
              const next = { ...b };
              delete next[data.task_id];
              return next;
            });
          }
          addFeed(
            `Task #${data.task_id} → ${data.status}`,
            data.status === 'running' ? '#ffb800' : data.status === 'failed' ? '#ff3366' : '#00ff88',
          );
          break;

        case 'task_message':
          // Final text supersedes the stream buffer for this turn
          if (data.role === 'assistant') {
            setStreamBuffers((b) => {
              const next = { ...b };
              delete next[data.task_id];
              return next;
            });
          }
          break;

        case 'task_token':
          // Live chunk — accumulate even if this task isn't on screen
          if (data.delta) {
            setStreamBuffers((b) => ({
              ...b,
              [data.task_id]: (b[data.task_id] || '') + data.delta,
            }));
          }
          break;

        case 'approval_required':
          addFeed(`⚠ Approval requested: ${data.tool_name} (task #${data.task_id})`, '#ff3366');
          api.getPendingApprovals().then(setApprovals).catch(() => {});
          break;

        case 'approval_resolved':
          setApprovals((a) => a.filter((x) => x.id !== data.approval_id));
          addFeed(`Approval resolved: ${data.status}`, data.status === 'approved' ? '#00ff88' : '#ff3366');
          break;
      }
    });
    return unsubscribe;
  }, [refreshAll, addFeed]);

  // ── Polling fallback: only while the WS is down ──
  useEffect(() => {
    if (wsStatus === 'connected') return;
    const id = setInterval(refreshAll, 5000);
    return () => clearInterval(id);
  }, [wsStatus, refreshAll]);

  const value: LiveContextValue = {
    tasks,
    approvals,
    wsStatus,
    serverReachable,
    streamBuffers,
    feed,
    refreshAll,
    subscribe: (h) => wsManager.subscribe(h),
    updateTaskLocal: (task) =>
      setTasks((ts) => {
        const idx = ts.findIndex((t) => t.id === task.id);
        if (idx === -1) return [task, ...ts];
        const next = [...ts];
        next[idx] = task;
        return next;
      }),
  };

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveContextValue {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error('useLive must be used inside LiveProvider');
  return ctx;
}
