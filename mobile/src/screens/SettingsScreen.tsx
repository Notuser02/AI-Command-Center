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

      {/* Online provider — bring your own API key */}
      <OnlineProviderCard />

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

    </ScrollView>
  );
}

const ONLINE_PRESETS = [
  { label: 'Nebius', url: 'https://api.studio.nebius.ai/v1' },
  { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { label: 'Groq', url: 'https://api.groq.com/openai/v1' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { label: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
];

function OnlineProviderCard() {
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState<string>('checking…');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getOnlineConfig().then((cfg) => {
      setBaseUrl(cfg.base_url || '');
      setStatus(
        cfg.api_key_set
          ? `✓ Key set${cfg.base_url ? ' · ' + cfg.base_url.replace(/^https?:\/\//, '') : ''}`
          : 'Not configured',
      );
    }).catch(() => setStatus('Server unreachable'));
  }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.saveOnlineConfig({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      });
      setApiKey('');
      const count = res.models?.length ?? 0;
      setStatus(`✓ Key set${res.base_url ? ' · ' + res.base_url.replace(/^https?:\/\//, '') : ''} — ${count} models available`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>ONLINE PROVIDER (API KEY)</Text>
      <Text style={styles.hint}>
        Use any online model service — Nebius, OpenRouter, Groq, OpenAI,
        DeepSeek or any OpenAI-compatible API. The key is stored only on your PC.
      </Text>
      <Text style={[styles.dim, { marginTop: 2 }]}>{status}</Text>

      <View style={styles.chipRow}>
        {ONLINE_PRESETS.map((p) => (
          <Pressable key={p.label} onPress={() => setBaseUrl(p.url)} style={[styles.chip, baseUrl === p.url && styles.chipActive]}>
            <Text style={[styles.chipText, baseUrl === p.url && styles.chipTextActive]}>{p.label}</Text>
          </Pressable>
        ))}
      </View>

      <TextInput
        style={styles.input}
        value={baseUrl}
        onChangeText={setBaseUrl}
        placeholder="Base URL, e.g. https://openrouter.ai/api/v1"
        placeholderTextColor={colors.dim}
        autoCapitalize="none"
        autoCorrect={false}
      />
      <TextInput
        style={[styles.input, { color: '#fff' }]}
        value={apiKey}
        onChangeText={setApiKey}
        placeholder="API key (paste here, e.g. sk-...)"
        placeholderTextColor={colors.dim}
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable style={[styles.primaryBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={save}>
        <Text style={styles.primaryBtnText}>{busy ? 'TESTING…' : 'TEST & SAVE'}</Text>
      </Pressable>
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
  error: { color: colors.red, fontSize: 12 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderColor: colors.border, borderWidth: 1, borderRadius: 4, paddingHorizontal: 10, paddingVertical: 6 },
  chipActive: { borderColor: colors.cyan, backgroundColor: 'rgba(0,240,255,0.12)' },
  chipText: { color: colors.text, fontSize: 12 },
  chipTextActive: { color: colors.cyan, fontWeight: '700' },
});
