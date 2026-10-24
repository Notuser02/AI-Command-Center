// Small persistence helpers (AsyncStorage works on native and web).

import AsyncStorage from '@react-native-async-storage/async-storage';

const KEYS = {
  serverUrl: '@acc/serverUrl',
  provider: '@acc/provider',
  model: '@acc/model',
  chatTaskId: '@acc/chatTaskId',
};

export async function loadString(key: string): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(key);
  } catch {
    return null;
  }
}

export async function saveString(key: string, value: string) {
  try {
    await AsyncStorage.setItem(key, value);
  } catch {
    // storage full / unavailable — non-fatal
  }
}

export const StorageKeys = KEYS;
