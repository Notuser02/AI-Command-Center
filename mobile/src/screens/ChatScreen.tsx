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
  const [toolsByModel, setToolsByModel] = useState<Record<string, boolean>>({});
  const [model, setModel] = useState(defModel);
  const [chatProvider, setChatProvider] = useState('local');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const scrollRef = useRef<ComponentRef<typeof ScrollView>>(null);

  // ── Find or create the persistent "Mobile Chat" workspace ──
  // One thread per provider (local / online), so switching provider in the
  // chat header switches to that provider's conversation.
  // Uses a ref for the current model so switching models doesn't re-run
  // this (which would reset the user's choice).
  const modelRef = useRef(model);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);

  const chatTaskKey = (p: string) => StorageKeys.chatTaskId + ':' + p;

  const ensureChatTask = useCallback(async (provider: string) => {
    setBooting(true);
    try {
      const saved = await loadString(chatTaskKey(provider));
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
        name: provider === 'online' ? 'Mobile Chat (online)' : 'Mobile Chat',
        task: 'Chat thread from the mobile app.',
        provider,
        model: modelRef.current,
      });
      await saveString(chatTaskKey(provider), String(t.id));
      setTask(t);
    } catch (e: any) {
      setError(`Could not reach backend: ${e.message}`);
    } finally {
      setBooting(false);
    }
  }, [defProvider, defModel]);

  useEffect(() => {
    ensureChatTask(chatProvider);
    api.getModels().then(setModels).catch(() => {});
    api.getModelsDetail().then((detail) => {
      const map: Record<string, boolean> = {};
      (detail.local || []).forEach((m) => { map[m.name] = m.tools; });
      (detail.online || []).forEach((m) => { map[m.name] = m.tools; });
      setToolsByModel(map);
    }).catch(() => {});
  }, [ensureChatTask, chatProvider]);

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
        name: chatProvider === 'online' ? 'Mobile Chat (online)' : 'Mobile Chat',
        task: 'Chat thread from the mobile app.',
        provider: chatProvider,
        model,
      });
      await saveString(chatTaskKey(chatProvider), String(t.id));
      setTask(t);
      refreshAll();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const modelList = (chatProvider === 'local' ? models?.local : models?.online) || [];

  const switchProvider = (p: string) => {
    setChatProvider(p);
    const list = (p === 'local' ? models?.local : models?.online) || [];
    if (list.length && !list.includes(model)) setModel(list[0]);
  };

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
      {/* Chat header: provider + model pickers + new chat */}
      <View style={styles.header}>
        <Pressable onPress={() => switchProvider('local')} style={[styles.chip, chatProvider === 'local' && styles.chipActive]}>
          <Text style={[styles.chipText, chatProvider === 'local' && styles.chipTextActive]}>Local</Text>
        </Pressable>
        <Pressable onPress={() => switchProvider('online')} style={[styles.chip, chatProvider === 'online' && styles.chipActive]}>
          <Text style={[styles.chipText, chatProvider === 'online' && styles.chipTextActive]}>Online</Text>
        </Pressable>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, flex: 1 }}>
          {modelList.map((m) => (
            <Pressable key={m} onPress={() => setModel(m)} style={[styles.chip, model === m && styles.chipActive]}>
              <Text style={[styles.chipText, model === m && styles.chipTextActive]} numberOfLines={1}>
                {m}{toolsByModel[m] === false ? ' · no tools' : ''}
              </Text>
            </Pressable>
          ))}
          {modelList.length === 0 && (
            <Text style={styles.dim}>{chatProvider === 'online' ? 'No online models — add an API key in Settings' : 'No models — check Settings'}</Text>
          )}
        </ScrollView>
        <Pressable onPress={newChat} style={styles.newChat}>
          <Text style={styles.newChatText}>+ NEW</Text>
        </Pressable>
      </View>
      {modelList.some((m) => toolsByModel[m] === false) ? (
        <Text style={styles.toolsHint}>
          "no tools" models answer from memory only — for web_search / files pick another.
        </Text>
      ) : null}

      <ScrollView ref={scrollRef} style={styles.stream} contentContainerStyle={{ padding: 12 }}>
        {/* Welcome state — the AI Agent Workspace branding, like the PC home screen */}
        {(task?.messages?.length ?? 0) === 0 && !running && (
          <View style={styles.emptyWrap}>
            <Text style={styles.emptyTitle}>[ AI AGENT WORKSPACE ]</Text>
            <Text style={styles.emptySub}>
              Chat with your PC's local models — responses stream live and your
              history is kept on the PC.
            </Text>
            <Text style={styles.emptyHint}>Pick a model above · send the first message below</Text>
          </View>
        )}
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
  emptyWrap: { alignItems: 'center', gap: 10, paddingVertical: 60, paddingHorizontal: 20 },
  emptyTitle: { color: colors.cyan, fontSize: 18, fontWeight: '700', textAlign: 'center' },
  emptySub: { color: colors.text, fontSize: 13, textAlign: 'center', lineHeight: 19 },
  emptyHint: { color: colors.dim, fontSize: 11, textAlign: 'center' },
  rowCenter: { flexDirection: 'row', alignItems: 'center' },
  dim: { color: colors.dim, fontSize: 12 },
  toolsHint: {
    color: colors.dim, fontSize: 10,
    paddingHorizontal: 10, paddingVertical: 3,
    backgroundColor: colors.panel, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
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
