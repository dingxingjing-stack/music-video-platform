/**
 * useSessionStorage — Persists TrackStudio workflow state to localStorage.
 *
 * Provides load / save / reset with safe JSON parsing and versioning.
 */

import { useCallback, useState } from 'react';
import {
  PersistedSession,
  STORAGE_KEY,
  STORAGE_VERSION,
  defaultPersisted,
} from '../types/trackStudio';

function loadRaw(): PersistedSession {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultPersisted();
    const parsed = JSON.parse(raw);
    return { ...defaultPersisted(), ...parsed, version: STORAGE_VERSION };
  } catch {
    return defaultPersisted();
  }
}

function saveRaw(session: PersistedSession): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Storage full or unavailable — silent fail
  }
}

export function useSessionStorage() {
  const [session, setSession] = useState<PersistedSession>(loadRaw);

  const save = useCallback(
    (partial: Partial<PersistedSession>) => {
      setSession((prev) => {
        const next = { ...prev, ...partial, version: STORAGE_VERSION };
        saveRaw(next);
        return next;
      });
    },
    [],
  );

  const reset = useCallback(() => {
    const fresh = defaultPersisted();
    setSession(fresh);
    saveRaw(fresh);
  }, []);

  return { session, setSession: save, reset };
}
