// Task detail: conversation + tool logs, live streaming, follow-up messages,
// and lifecycle actions exactly as the backend supports them:
//   STOP (while running) · FINISH (pending/idle/failed/cancelled) · DELETE (not running)

import React, { useCallback, useEffect, useRef, useState, type ComponentRef } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useLive } from '../context/LiveContext';
import { api } from '../api';
import { colors } from '../theme';
import { MessageBubble, StatusBadge, StreamBubble } from '../components';
import { confirmDialog } from '../util';
import type { RootStackParamList } from '../nav';
import type { Task } from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'TaskDetail'>;

export default function TaskDetailScreen({ navigation, route }: Props) {
  const taskId = route.params.id;
  const { streamBuffers, subscribe } = useLive();
  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);

  const load = useCallback(async () => {
    try {
      const t = await api.getTask(taskId);
      setTask(t);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [taskId]);

  useEffect(() => {
    load();
  }, [load]);

  // React to WS events for THIS task: refetch on final message / status change,
  // navigate back if it got deleted elsewhere.
  useEffect(() => {
    return subscribe((msg) => {
      const { event, data } = msg;
      if (event === 'task_message' && data.task_id === taskId) load();
      if (event === 'task_status_changed' && data.task_id === taskId) load();
      if (event === 'task_deleted' && data.task_id === taskId) navigation.goBack();
    });
  }, [subscribe, taskId, load, navigation]);

  const running = task?.status === 'running';
  const buffer = streamBuffers[taskId] || '';

  useEffect(() => {
    // keep the newest content in view while streaming
    scrollRef.current?.scrollToEnd?.({ animated: false });
  }, [task?.messages?.length, buffer]);

  const send = async () => {
    const text = input.trim();
    if (!text || running) return;
    setInput('');
    setBusy(true);
    try {
      await api.sendMessage(taskId, text);
    } catch (e: any) {
      setError(e.message);
      setInput(text);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    try { await api.stopTask(taskId); } catch (e: any) { setError(e.message); }
  };

  const finish = async () => {
    try { await api.completeTask(taskId); } catch (e: any) { setError(e.message); }
  };

  const remove = async () => {
    if (!(await confirmDialog(`Permanently delete this task and its history?`))) return;
    try {
      await api.deleteTask(taskId);
      navigation.goBack();
    } catch (e: any) { setError(e.message); }
  };

  if (!task) {
    return (
      <View style={[styles.screen, styles.center]}>
        {error ? (
          <Text style={styles.error}>{error}</Text>
        ) : (
          <ActivityIndicator color={colors.cyan} />
        )}
      </View>
    );
  }

  const displayName = task.name || `TASK-${task.id}`;
  const canFinish = ['pending', 'idle', 'failed', 'cancelled'].includes(task.status);
  const canDelete = !running;
  const logs = (task.logs || []).filter(
    (l: any) => l.type === 'tool_call' || l.type === 'tool_result' || l.type === 'approval_required',
  );

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={{ flexShrink: 1, gap: 4 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={styles.title} numberOfLines={1}>{displayName}</Text>
            <StatusBadge status={task.status} />
          </View>
          {task.task ? <Text style={styles.dim} numberOfLines={1}>{task.task}</Text> : null}
          <Text style={styles.dim}>
            {task.provider} · <Text style={{ color: colors.cyan }}>{task.model || 'qwen3.5:9b'}</Text>
          </Text>
        </View>
      </View>

      {/* Actions — same visibility rules as the PC dashboard */}
      <View style={styles.actionRow}>
        {running && (
          <Pressable style={[styles.actionBtn, styles.actionStop]} onPress={stop}>
            <Text style={styles.actionStopText}>■ STOP RESPONSE</Text>
          </Pressable>
        )}
        {canFinish && (
          <Pressable style={[styles.actionBtn, styles.actionFinish]} onPress={finish}>
            <Text style={styles.actionFinishText}>✔ FINISH</Text>
          </Pressable>
        )}
        {canDelete && (
          <Pressable style={[styles.actionBtn, styles.actionDelete]} onPress={remove}>
            <Text style={styles.actionDeleteText}>✖ DELETE</Text>
          </Pressable>
        )}
      </View>

      {/* Conversation */}
      <ScrollView ref={scrollRef} style={styles.stream} contentContainerStyle={{ padding: 12, paddingBottom: 20 }}>
        {(task.messages || []).map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}

        {running && buffer.length > 0 && <StreamBubble text={buffer} />}
        {running && buffer.length === 0 && (
          <View style={[styles.row, { padding: 8, gap: 8 }]}>
            <ActivityIndicator color={colors.cyan} size="small" />
            <Text style={styles.dim}>Agent is working…</Text>
          </View>
        )}

        {logs.length > 0 && (
          <View style={{ marginTop: 12, gap: 6 }}>
            <Text style={styles.logsTitle}>TOOL ACTIVITY ({logs.length})</Text>
            {logs.map((l: any, i: number) => (
              <Text key={i} style={styles.logLine}>
                {l.type === 'tool_call'
                  ? `⚡ ${l.tool}(${JSON.stringify(l.arguments || {}).slice(0, 80)})`
                  : l.type === 'approval_required'
                    ? `⚠ ${l.tool} — needs your approval`
                    : `📋 ${l.tool}: ${String(l.result || '').slice(0, 120)}`}
              </Text>
            ))}
          </View>
        )}
      </ScrollView>

      {error ? <Text style={styles.errorBar}>{error}</Text> : null}

      {/* Input */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder={running ? 'Agent is responding…' : 'Type an instruction…'}
          placeholderTextColor={colors.dim}
          editable={!running && !busy}
          multiline
        />
        <Pressable
          style={[styles.sendBtn, (running || busy || !input.trim()) && { opacity: 0.4 }]}
          disabled={running || busy || !input.trim()}
          onPress={send}
        >
          <Text style={styles.sendBtnText}>SEND</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colors.bg, flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center' },
  header: {
    paddingHorizontal: 14,
    paddingTop: 14,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { color: '#fff', fontSize: 17, fontWeight: '700', flexShrink: 1 },
  dim: { color: colors.dim, fontSize: 12 },
  row: { flexDirection: 'row', alignItems: 'center' },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  actionBtn: {
    borderRadius: 4,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderWidth: 1,
  },
  actionStop: { backgroundColor: 'rgba(255,184,0,0.15)', borderColor: colors.yellow },
  actionStopText: { color: colors.yellow, fontWeight: '700', fontSize: 12 },
  actionFinish: { backgroundColor: 'rgba(0,255,136,0.12)', borderColor: colors.green },
  actionFinishText: { color: colors.green, fontWeight: '700', fontSize: 12 },
  actionDelete: { backgroundColor: 'rgba(255,51,102,0.12)', borderColor: colors.red },
  actionDeleteText: { color: colors.red, fontWeight: '700', fontSize: 12 },
  stream: { flex: 1, backgroundColor: '#05070a' },
  logsTitle: { color: colors.dim, fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  logLine: { color: colors.text, fontSize: 11, lineHeight: 17 },
  error: { color: colors.red, fontSize: 12, padding: 14 },
  errorBar: { color: colors.red, fontSize: 11, paddingHorizontal: 14, paddingVertical: 4 },
  inputRow: {
    flexDirection: 'row',
    gap: 8,
    padding: 10,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.panel,
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    backgroundColor: colors.inputBg,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 4,
    color: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 13,
    minHeight: 40,
    maxHeight: 110,
  },
  sendBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 4,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  sendBtnText: { color: '#000', fontWeight: '700', fontSize: 12 },
});
