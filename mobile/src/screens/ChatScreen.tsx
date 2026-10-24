// Chat: talks to the backend through a task workspace ("Mobile Chat") —
// the same POST /tasks/{id}/messages endpoint the PC dashboard uses, so the
// phone gets live token streaming (WS task_token), persistent history, and
// STOP mid-answer. The thread is also visible on the PC dashboard.

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
import { useLive } from '../context/LiveContext';
import { useSettings } from '../context/SettingsContext';
import { api } from '../api';
import { colors } from '../theme';
import { MessageBubble, StreamBubble } from '../components';
import { loadString, saveString, StorageKeys } from '../storage';
import type { ModelsResponse, Task } from '../types';

export default function ChatScreen() {
  const { provider: defProvider, model: defModel } = useSettings();
  const { streamBuffers, subscribe, refreshAll } = useLive();

  const [task, setTask] = useState<Task | null>(null);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [model, setModel] = useState(defModel);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);

  // ── Find or create the persistent "Mobile Chat" workspace ──
  // Uses a ref for the current model so switching models doesn't re-run
  // this (which would reset the user's choice).
  const modelRef = useRef(model);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);

  const ensureChatTask = useCallback(async () => {
    setBooting(true);
    try {
      const saved = await loadString(StorageKeys.chatTaskId);
      if (saved) {
        const t = await api.getTask(Number(saved));
        setTask(t);
        setModel(t.model || defModel);
        setBooting(false);
        return;
      }
    } catch {
      // saved task vanished (deleted on PC) — fall through and create a new one
    }
    try {
      const t = await api.createTask({
        name: 'Mobile Chat',
        task: 'Chat thread from the mobile app.',
        provider: defProvider,
        model: modelRef.current,
      });
      await saveString(StorageKeys.chatTaskId, String(t.id));
      setTask(t);
    } catch (e: any) {
      setError(`Could not reach backend: ${e.message}`);
    } finally {
      setBooting(false);
    }
  }, [defProvider, defModel]);

  useEffect(() => {
    ensureChatTask();
    api.getModels().then(setModels).catch(() => {});
  }, [ensureChatTask]);

  const load = useCallback(async () => {
    if (!task) return;
    try {
      setTask(await api.getTask(task.id));
    } catch {}
  }, [task]);

  // Live updates for this thread
  useEffect(() => {
    return subscribe((msg) => {
      if (!task) return;
      if (msg.event === 'task_message' && msg.data.task_id === task.id) load();
      if (msg.event === 'task_status_changed' && msg.data.task_id === task.id) load();
    });
  }, [subscribe, task, load]);

  const running = task?.status === 'running';
  const buffer = task ? streamBuffers[task.id] || '' : '';

  useEffect(() => {
    scrollRef.current?.scrollToEnd?.({ animated: false });
  }, [task?.messages?.length, buffer]);

  const send = async () => {
    const text = input.trim();
    if (!text || !task || running) return;
    setInput('');
    setBusy(true);
    try {
      await api.sendMessage(task.id, text);
    } catch (e: any) {
      setError(e.message);
      setInput(text);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!task) return;
    try { await api.stopTask(task.id); } catch (e: any) { setError(e.message); }
  };

  const newChat = async () => {
    if (!task) return;
    try {
      const t = await api.createTask({
        name: 'Mobile Chat',
        task: 'Chat thread from the mobile app.',
        provider: defProvider,
        model,
      });
      await saveString(StorageKeys.chatTaskId, String(t.id));
      setTask(t);
      refreshAll();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const modelList = models?.local || [];

  if (booting) {
    return (
      <View style={[styles.screen, styles.center]}>
        <ActivityIndicator color={colors.cyan} />
        <Text style={styles.dim}>Connecting to your PC…</Text>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Chat header: model picker + new chat */}
      <View style={styles.header}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {modelList.map((m) => (
            <Pressable key={m} onPress={() => setModel(m)} style={[styles.chip, model === m && styles.chipActive]}>
              <Text style={[styles.chipText, model === m && styles.chipTextActive]}>{m}</Text>
            </Pressable>
          ))}
          {modelList.length === 0 && <Text style={styles.dim}>No models — check Settings</Text>}
        </ScrollView>
        <Pressable onPress={newChat} style={styles.newChat}>
          <Text style={styles.newChatText}>+ NEW CHAT</Text>
        </Pressable>
      </View>

      <ScrollView ref={scrollRef} style={styles.stream} contentContainerStyle={{ padding: 12 }}>
        {(task?.messages || []).map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {running && buffer.length > 0 && <StreamBubble text={buffer} />}
        {running && buffer.length === 0 && (
          <View style={[styles.rowCenter, { padding: 8, gap: 8 }]}>
            <ActivityIndicator color={colors.cyan} size="small" />
            <Text style={styles.dim}>Thinking…</Text>
          </View>
        )}
      </ScrollView>

      {error ? <Text style={styles.errorBar}>{error}</Text> : null}

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder={running ? 'Agent is responding…' : 'Message your PC…'}
          placeholderTextColor={colors.dim}
          editable={!running && !busy}
          multiline
        />
        {running ? (
          <Pressable style={[styles.sendBtn, styles.stopBtn]} onPress={stop}>
            <Text style={styles.stopBtnText}>■ STOP</Text>
          </Pressable>
        ) : (
          <Pressable
            style={[styles.sendBtn, (!input.trim() || busy) && { opacity: 0.4 }]}
            disabled={!input.trim() || busy}
            onPress={send}
          >
            <Text style={styles.sendBtnText}>SEND</Text>
          </Pressable>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colors.bg, flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center', gap: 10 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.panel,
  },
  chip: {
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  chipActive: { borderColor: colors.cyan, backgroundColor: 'rgba(0,240,255,0.12)' },
  chipText: { color: colors.text, fontSize: 11 },
  chipTextActive: { color: colors.cyan, fontWeight: '700' },
  newChat: { paddingHorizontal: 8, paddingVertical: 4 },
  newChatText: { color: colors.cyan, fontSize: 12, fontWeight: '700' },
  stream: { flex: 1, backgroundColor: '#05070a' },
  rowCenter: { flexDirection: 'row', alignItems: 'center' },
  dim: { color: colors.dim, fontSize: 12 },
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
  sendBtn: { backgroundColor: colors.cyan, borderRadius: 4, paddingHorizontal: 16, paddingVertical: 10 },
  sendBtnText: { color: '#000', fontWeight: '700', fontSize: 12 },
  stopBtn: { backgroundColor: 'rgba(255,184,0,0.15)', borderColor: colors.yellow, borderWidth: 1 },
  stopBtnText: { color: colors.yellow, fontWeight: '700', fontSize: 12 },
});
