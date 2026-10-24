// Task list with pull-to-refresh + New Task form (reuses POST /tasks).

import React, { useEffect, useState } from 'react';
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useLive } from '../context/LiveContext';
import { useSettings } from '../context/SettingsContext';
import { api } from '../api';
import { colors } from '../theme';
import { TaskCard } from '../components';
import type { ModelsResponse } from '../types';
import type { MainTabsParamList, RootStackParamList } from '../nav';

// TasksScreen lives in the bottom tabs but pushes screens onto the root
// stack (TaskDetail, NewTask) — hence the composite navigation type.
type Props = CompositeScreenProps<
  BottomTabScreenProps<MainTabsParamList, 'Tasks'>,
  NativeStackScreenProps<RootStackParamList>
>;

export default function TasksScreen({ navigation }: Props) {
  const { tasks, refreshAll, wsStatus } = useLive();
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await refreshAll();
    setRefreshing(false);
  };

  return (
    <View style={styles.screen}>
      <FlatList
        data={tasks}
        keyExtractor={(t) => String(t.id)}
        contentContainerStyle={{ padding: 12, paddingBottom: 80 }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.cyan} />
        }
        ListHeaderComponent={
          <View style={styles.headerRow}>
            <Text style={styles.header}>TASK WORKSPACES</Text>
            <Pressable style={styles.newBtn} onPress={() => navigation.navigate('NewTask')}>
              <Text style={styles.newBtnText}>+ NEW TASK</Text>
            </Pressable>
          </View>
        }
        ListEmptyComponent={
          <Text style={styles.empty}>
            No tasks yet — create one, or check the server in Settings.
            {'\n'}(Live stream: {wsStatus})
          </Text>
        }
        renderItem={({ item }) => (
          <TaskCard task={item} onPress={() => navigation.navigate('TaskDetail', { id: item.id })} />
        )}
      />
    </View>
  );
}

export function NewTaskScreen({ navigation }: NativeStackScreenProps<RootStackParamList, 'NewTask'>) {
  const { provider: defProvider, model: defModel } = useSettings();
  const { refreshAll } = useLive();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [provider, setProvider] = useState(defProvider);
  const [model, setModel] = useState(defModel);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getModels().then(setModels).catch(() => {});
  }, []);

  const modelList = (provider === 'local' ? models?.local : models?.online) || [];

  const create = async () => {
    if (!name.trim() && !description.trim()) {
      setError('Give the task at least a name or a description.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createTask({
        name: name.trim() || null,
        task: description.trim(),
        provider,
        model: model || models?.default.local,
      });
      await refreshAll();
      navigation.goBack();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ padding: 14, gap: 12 }}>
      <Text style={styles.label}>Task name (optional — blank becomes TASK-N)</Text>
      <TextInput
        style={styles.input}
        value={name}
        onChangeText={setName}
        placeholder="e.g. Refactor Research"
        placeholderTextColor={colors.dim}
      />

      <Text style={styles.label}>Description (optional context for the agent)</Text>
      <TextInput
        style={[styles.input, { minHeight: 80 }]}
        value={description}
        onChangeText={setDescription}
        multiline
        placeholder="What is this workspace for?"
        placeholderTextColor={colors.dim}
      />

      <Text style={styles.label}>Provider</Text>
      <View style={styles.chipRow}>
        {['local', 'online'].map((p) => (
          <Pressable
            key={p}
            onPress={() => setProvider(p)}
            style={[styles.chip, provider === p && styles.chipActive]}
          >
            <Text style={[styles.chipText, provider === p && styles.chipTextActive]}>
              {p === 'local' ? 'Local (Ollama)' : 'Online'}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Model</Text>
      <View style={styles.chipRow}>
        {modelList.length === 0 && <Text style={styles.emptySmall}>No models listed</Text>}
        {modelList.map((m) => (
          <Pressable key={m} onPress={() => setModel(m)} style={[styles.chip, model === m && styles.chipActive]}>
            <Text style={[styles.chipText, model === m && styles.chipTextActive]}>{m}</Text>
          </Pressable>
        ))}
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Pressable style={[styles.primaryBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={create}>
        <Text style={styles.primaryBtnText}>{busy ? 'CREATING…' : 'CREATE TASK'}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colors.bg, flex: 1 },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  header: { color: colors.cyan, fontWeight: '700', fontSize: 13, letterSpacing: 1 },
  newBtn: {
    borderColor: colors.cyan,
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: 'rgba(0,240,255,0.1)',
  },
  newBtnText: { color: colors.cyan, fontWeight: '700', fontSize: 12 },
  empty: { color: colors.dim, fontSize: 13, textAlign: 'center', marginTop: 40, lineHeight: 20 },
  emptySmall: { color: colors.dim, fontSize: 12 },
  label: { color: colors.text, fontSize: 12 },
  input: {
    backgroundColor: colors.inputBg,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 4,
    color: '#fff',
    padding: 10,
    fontSize: 13,
    textAlignVertical: 'top',
  },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  chipActive: { borderColor: colors.cyan, backgroundColor: 'rgba(0,240,255,0.12)' },
  chipText: { color: colors.text, fontSize: 12 },
  chipTextActive: { color: colors.cyan, fontWeight: '700' },
  primaryBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 4,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 6,
  },
  primaryBtnText: { color: '#000', fontWeight: '700', letterSpacing: 1 },
  error: { color: colors.red, fontSize: 12 },
});
