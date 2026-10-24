// Small shared UI pieces styled like the PC dashboard.

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, statusColor } from './theme';
import type { Approval, Task, TaskMessage } from './types';

export function StatusBadge({ status }: { status: string }) {
  const color = statusColor(status);
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <Text style={[styles.badgeText, { color }]}>{status.toUpperCase()}</Text>
    </View>
  );
}

export function TaskCard({ task, onPress }: { task: Task; onPress: () => void }) {
  const displayName = task.name || `TASK-${task.id}`;
  return (
    <PressableCard onPress={onPress}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardTitle} numberOfLines={1}>
          {displayName}
          {task.name ? <Text style={styles.cardId}> #{task.id}</Text> : null}
        </Text>
        <StatusBadge status={task.status} />
      </View>
      {task.task ? (
        <Text style={styles.cardDesc} numberOfLines={2}>
          {task.task}
        </Text>
      ) : null}
      <View style={styles.cardMetaRow}>
        <Text style={styles.cardMeta}>
          {task.provider} · <Text style={{ color: colors.cyan }}>{task.model || 'qwen3.5:9b'}</Text>
        </Text>
        <Text style={styles.cardMeta}>{task.messages?.length ?? 0} msgs</Text>
      </View>
    </PressableCard>
  );
}

export function PressableCard({
  children,
  onPress,
}: {
  children: React.ReactNode;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={styles.cardShell}>
      <View style={styles.cardPress}>{children}</View>
    </Pressable>
  );
}

export function MessageBubble({ message }: { message: TaskMessage }) {
  const isUser = message.role === 'user';
  return (
    <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
      <Text style={[styles.bubbleAuthor, { color: isUser ? colors.cyan : colors.green }]}>
        {isUser ? 'YOU' : 'AGENT'}
      </Text>
      <Text style={styles.bubbleText} selectable>
        {message.content}
      </Text>
    </View>
  );
}

export function StreamBubble({ text }: { text: string }) {
  return (
    <View style={[styles.bubble, styles.bubbleAssistant, { borderLeftColor: colors.cyan }]}>
      <Text style={[styles.bubbleAuthor, { color: colors.cyan }]}>AGENT RESPONDING ▌</Text>
      <Text style={styles.bubbleText} selectable>
        {text}
      </Text>
    </View>
  );
}

export function ApprovalBanner({
  approval,
  onApprove,
  onDeny,
}: {
  approval: Approval;
  onApprove: () => void;
  onDeny: () => void;
}) {
  return (
    <View style={styles.approval}>
      <Text style={styles.approvalTitle}>⚠ APPROVAL REQUIRED</Text>
      <Text style={styles.approvalText}>
        Task #{approval.task_id} wants to run '{approval.tool_name}'
        {approval.arguments ? ` — ${JSON.stringify(approval.arguments).slice(0, 120)}` : ''}
      </Text>
      <View style={styles.approvalButtons}>
        <Text accessibilityRole="button" style={[styles.btn, styles.btnDeny]} onPress={onDeny}>
          DENY
        </Text>
        <Text accessibilityRole="button" style={[styles.btn, styles.btnApprove]} onPress={onApprove}>
          APPROVE
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderWidth: 1,
    borderRadius: 3,
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  badgeText: { fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },
  cardShell: {
    backgroundColor: colors.panel,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 6,
    marginBottom: 8,
  },
  cardPress: { padding: 12 },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  cardTitle: { color: '#ffffff', fontWeight: '700', fontSize: 14, flexShrink: 1 },
  cardId: { color: colors.dim, fontWeight: '400', fontSize: 12 },
  cardDesc: { color: colors.text, fontSize: 12, marginTop: 4 },
  cardMetaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 6,
  },
  cardMeta: { color: colors.dim, fontSize: 11 },
  bubble: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
  },
  bubbleUser: { alignSelf: 'flex-end', backgroundColor: '#121c2c', maxWidth: '90%' },
  bubbleAssistant: {
    alignSelf: 'flex-start',
    backgroundColor: '#0c121c',
    borderLeftWidth: 3,
    borderLeftColor: colors.green,
    maxWidth: '95%',
  },
  bubbleAuthor: { fontSize: 10, fontWeight: '700', marginBottom: 4 },
  bubbleText: { color: colors.text, fontSize: 13, lineHeight: 19 },
  approval: {
    backgroundColor: 'rgba(255,51,102,0.12)',
    borderColor: colors.red,
    borderWidth: 1,
    borderRadius: 6,
    padding: 12,
    marginBottom: 10,
  },
  approvalTitle: { color: colors.red, fontWeight: '700', fontSize: 12, marginBottom: 4 },
  approvalText: { color: colors.text, fontSize: 12, marginBottom: 10 },
  approvalButtons: { flexDirection: 'row', gap: 10, justifyContent: 'flex-end' },
  btn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 4,
    overflow: 'hidden',
    fontWeight: '700',
    fontSize: 12,
  },
  btnApprove: { backgroundColor: 'rgba(0,255,136,0.15)', color: colors.green, borderColor: colors.green, borderWidth: 1 },
  btnDeny: { backgroundColor: 'rgba(255,51,102,0.15)', color: colors.red, borderColor: colors.red, borderWidth: 1 },
});
