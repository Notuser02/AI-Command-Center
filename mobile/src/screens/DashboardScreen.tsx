// Dashboard: connection state, models, task overview, approvals, live feed.

import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLive } from '../context/LiveContext';
import { useSettings } from '../context/SettingsContext';
import { api } from '../api';
import { colors, statusColor } from '../theme';
import { ApprovalBanner } from '../components';
import type { ModelsResponse } from '../types';

export default function DashboardScreen() {
  const { serverUrl } = useSettings();
  const { wsStatus, serverReachable, tasks, approvals, feed, refreshAll } = useLive();
  const [models, setModels] = useState<ModelsResponse | null>(null);

  useEffect(() => {
    api.getModels().then(setModels).catch(() => setModels(null));
  }, [serverUrl]);

  const running = tasks.filter((t) => t.status === 'running').length;
  const idle = tasks.filter((t) => t.status === 'idle').length;
  const completed = tasks.filter((t) => t.status === 'completed').length;
  const failed = tasks.filter((t) => t.status === 'failed' || t.status === 'cancelled').length;

  const wsOk = wsStatus === 'connected';

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ padding: 14, gap: 12 }}>
      {/* Connection */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>BACKEND CONNECTION</Text>
        <View style={styles.row}>
          <View style={[styles.dot, { backgroundColor: serverReachable ? colors.green : colors.red }]} />
          <Text style={styles.value}>{serverReachable ? 'Reachable' : 'Unreachable'}</Text>
        </View>
        <View style={styles.row}>
          <View style={[styles.dot, { backgroundColor: wsOk ? colors.green : colors.yellow }]} />
          <Text style={styles.value}>
            Live stream: {wsStatus}
            {wsOk ? '' : ' (polling every 5s)'}
          </Text>
        </View>
        <Text style={styles.dim}>{serverUrl}</Text>
      </View>

      {/* Models */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>MODELS ON THIS PC</Text>
        {models ? (
          <>
            <Text style={styles.value}>
              {models.local.length} local model{models.local.length === 1 ? '' : 's'} · default{' '}
              <Text style={{ color: colors.cyan }}>{models.default.local}</Text>
            </Text>
            <Text style={styles.dim} numberOfLines={2}>
              {models.local.join(', ')}
            </Text>
          </>
        ) : (
          <Text style={styles.dim}>Model list unavailable</Text>
        )}
      </View>

      {/* Task overview */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>TASKS ({tasks.length} total)</Text>
        <View style={styles.statsRow}>
          <Stat label="running" value={running} color={statusColor('running')} />
          <Stat label="idle" value={idle} color={statusColor('idle')} />
          <Stat label="done" value={completed} color={statusColor('completed')} />
          <Stat label="ended" value={failed} color={statusColor('failed')} />
        </View>
      </View>

      {/* Approvals */}
      {approvals.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>PENDING APPROVALS ({approvals.length})</Text>
          {approvals.map((a) => (
            <ApprovalBanner
              key={a.id}
              approval={a}
              onApprove={() => api.resolveApproval(a.id, true).then(refreshAll).catch(() => {})}
              onDeny={() => api.resolveApproval(a.id, false).then(refreshAll).catch(() => {})}
            />
          ))}
        </View>
      )}

      {/* Live feed */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>LIVE ACTIVITY</Text>
        {feed.length === 0 ? (
          <Text style={styles.dim}>Waiting for events…</Text>
        ) : (
          feed.slice(0, 15).map((item) => (
            <Text key={item.id} style={styles.feedItem}>
              <Text style={styles.dim}>{item.time} </Text>
              <Text style={{ color: item.color }}>{item.text}</Text>
            </Text>
          ))
        )}
      </View>
    </ScrollView>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colors.bg, flex: 1 },
  card: {
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 6,
    padding: 12,
    gap: 6,
  },
  cardTitle: { color: colors.cyan, fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  value: { color: colors.text, fontSize: 13 },
  dim: { color: colors.dim, fontSize: 12 },
  statsRow: { flexDirection: 'row', gap: 10, marginTop: 4 },
  stat: {
    flex: 1,
    backgroundColor: colors.bg,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 6,
    alignItems: 'center',
    paddingVertical: 10,
  },
  statValue: { fontSize: 20, fontWeight: '700' },
  statLabel: { color: colors.dim, fontSize: 11, marginTop: 2 },
  feedItem: { fontSize: 12, lineHeight: 18 },
});
