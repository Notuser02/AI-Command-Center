// Settings: PC server address (never 'localhost'), connection test,
// default provider + model preferences.

import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSettings } from '../context/SettingsContext';
import { useLive } from '../context/LiveContext';
import { api, DEFAULT_SERVER_URL } from '../api';
import { colors } from '../theme';
import type { ModelsResponse } from '../types';

export default function SettingsScreen() {
  const { serverUrl, setServerUrl, provider, setProvider, model, setModel, persist, testConnection } =
    useSettings();
  const { refreshAll, wsStatus } = useLive();
  const [urlDraft, setUrlDraft] = useState(serverUrl);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setUrlDraft(serverUrl);
  }, [serverUrl]);

  useEffect(() => {
    api.getModels().then(setModels).catch(() => setModels(null));
  }, [serverUrl]);

  const modelList = (provider === 'local' ? models?.local : models?.online) || [];

  const save = async () => {
    setServerUrl(urlDraft.trim());
    await persist();
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
    refreshAll();
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ padding: 14, gap: 12 }}>
      {/* Server */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>PC SERVER ADDRESS</Text>
        <Text style={styles.hint}>
          Your PC's IP on the same Wi-Fi (run `ipconfig` on the PC → IPv4).{'\n'}
          Never use localhost — on the phone that means the phone itself.
        </Text>
        <TextInput
          style={styles.input}
          value={urlDraft}
          onChangeText={setUrlDraft}
          placeholder={`e.g. ${DEFAULT_SERVER_URL}`}
          placeholderTextColor={colors.dim}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <View style={styles.btnRow}>
          <Pressable
            style={styles.secondaryBtn}
            onPress={async () => setTestResult(await testConnection(urlDraft.trim()))}
          >
            <Text style={styles.secondaryBtnText}>TEST CONNECTION</Text>
          </Pressable>
          <Pressable style={styles.primaryBtn} onPress={save}>
            <Text style={styles.primaryBtnText}>{saved ? 'SAVED ✓' : 'SAVE'}</Text>
          </Pressable>
        </View>
        {testResult ? <Text style={styles.testResult}>{testResult}</Text> : null}
        <Text style={styles.dim}>Live stream: {wsStatus}</Text>
      </View>

      {/* Provider + model */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>DEFAULT PROVIDER</Text>
        <View style={styles.chipRow}>
          {['local', 'online'].map((p) => (
            <Pressable key={p} onPress={() => setProvider(p)} style={[styles.chip, provider === p && styles.chipActive]}>
              <Text style={[styles.chipText, provider === p && styles.chipTextActive]}>
                {p === 'local' ? 'Local (Ollama)' : 'Online'}
              </Text>
            </Pressable>
          ))}
        </View>

        <Text style={[styles.cardTitle, { marginTop: 8 }]}>DEFAULT MODEL</Text>
        <View style={styles.chipRow}>
          {modelList.length === 0 && <Text style={styles.dim}>No models listed (is the backend reachable?)</Text>}
          {modelList.map((m) => (
            <Pressable key={m} onPress={() => setModel(m)} style={[styles.chip, model === m && styles.chipActive]}>
              <Text style={[styles.chipText, model === m && styles.chipTextActive]}>{m}</Text>
            </Pressable>
          ))}
        </View>

        <Pressable style={[styles.primaryBtn, { marginTop: 10 }]} onPress={persist}>
          <Text style={styles.primaryBtnText}>SAVE PREFERENCES</Text>
        </Pressable>
      </View>

      {/* Connection help */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>CAN'T CONNECT?</Text>
        <Text style={styles.hint}>
          1. Backend must run with:{'\n'}
          <Text style={styles.code}>uvicorn main:app --host 0.0.0.0 --port 8000</Text>
          {'\n'}2. Allow it through Windows Firewall (admin PowerShell):{'\n'}
          <Text style={styles.code}>
            netsh advfirewall firewall add rule name="AI Command Center" dir=in action=allow protocol=TCP localport=8000
          </Text>
          {'\n'}3. Phone and PC must be on the same Wi-Fi network.
        </Text>
      </View>
    </ScrollView>
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
    gap: 8,
  },
  cardTitle: { color: colors.cyan, fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  hint: { color: colors.dim, fontSize: 12, lineHeight: 18 },
  code: { color: colors.green, fontFamily: 'monospace', fontSize: 11 },
  dim: { color: colors.dim, fontSize: 12 },
  input: {
    backgroundColor: colors.inputBg,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 4,
    color: '#fff',
    padding: 10,
    fontSize: 13,
  },
  btnRow: { flexDirection: 'row', gap: 8 },
  primaryBtn: {
    backgroundColor: colors.cyan,
    borderRadius: 4,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  primaryBtnText: { color: '#000', fontWeight: '700', fontSize: 12 },
  secondaryBtn: {
    borderColor: colors.cyan,
    borderWidth: 1,
    borderRadius: 4,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  secondaryBtnText: { color: colors.cyan, fontWeight: '700', fontSize: 12 },
  testResult: { color: colors.text, fontSize: 12 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderColor: colors.border, borderWidth: 1, borderRadius: 4, paddingHorizontal: 10, paddingVertical: 6 },
  chipActive: { borderColor: colors.cyan, backgroundColor: 'rgba(0,240,255,0.12)' },
  chipText: { color: colors.text, fontSize: 12 },
  chipTextActive: { color: colors.cyan, fontWeight: '700' },
});
