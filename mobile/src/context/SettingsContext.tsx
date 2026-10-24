// Settings: server URL + default provider/model, persisted in AsyncStorage.

import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, DEFAULT_SERVER_URL, setBaseUrl, wsUrl } from '../api';
import { loadString, saveString, StorageKeys } from '../storage';

interface SettingsState {
  serverUrl: string;
  provider: string; // 'local' | 'online'
  model: string;
  loaded: boolean; // hydrated from storage yet?
}

interface SettingsContextValue extends SettingsState {
  setServerUrl: (url: string) => void;
  setProvider: (p: string) => void;
  setModel: (m: string) => void;
  persist: () => Promise<void>;
  testConnection: (url?: string) => Promise<string>;
  activeWsUrl: () => string;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SettingsState>({
    serverUrl: DEFAULT_SERVER_URL,
    provider: 'local',
    model: 'qwen3.5:9b',
    loaded: false,
  });

  // Hydrate from storage once
  useEffect(() => {
    (async () => {
      const [url, provider, model] = await Promise.all([
        loadString(StorageKeys.serverUrl),
        loadString(StorageKeys.provider),
        loadString(StorageKeys.model),
      ]);
      const next = {
        serverUrl: url || DEFAULT_SERVER_URL,
        provider: provider || 'local',
        model: model || 'qwen3.5:9b',
        loaded: true,
      };
      setBaseUrl(next.serverUrl);
      setState((s) => ({ ...s, ...next }));
    })();
  }, []);

  const value: SettingsContextValue = {
    ...state,
    setServerUrl: (url) => setState((s) => ({ ...s, serverUrl: url })),
    setProvider: (p) => setState((s) => ({ ...s, provider: p })),
    setModel: (m) => setState((s) => ({ ...s, model: m })),
    persist: async () => {
      await Promise.all([
        saveString(StorageKeys.serverUrl, state.serverUrl),
        saveString(StorageKeys.provider, state.provider),
        saveString(StorageKeys.model, state.model),
      ]);
      setBaseUrl(state.serverUrl);
    },
    testConnection: async (url) => {
      const target = (url ?? state.serverUrl).trim().replace(/\/+$/, '');
      try {
        const res = await fetch(target + '/status', { method: 'GET' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        return `✓ Connected — ${body.status || 'server is running'}`;
      } catch (e: any) {
        return `✗ ${e.message || 'unreachable'} — check the PC IP, that the backend runs with --host 0.0.0.0, and the Windows Firewall rule`;
      }
    },
    activeWsUrl: () => wsUrl(),
  };

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings must be used inside SettingsProvider');
  return ctx;
}
