'use client';

import { create } from 'zustand';
import type { Preferences, PriceRange } from '@/types';
import { DEFAULT_PREFERENCES } from '@/types';
import { postPreferences, getOrCreateSessionId } from '@/services/api';

const PREFS_STORAGE_KEY = 'TM_PREFERENCES';

// ─── Debounce utility ───
let syncTimeout: ReturnType<typeof setTimeout> | null = null;

function debouncedSync(prefs: Preferences) {
  if (syncTimeout) clearTimeout(syncTimeout);
  syncTimeout = setTimeout(async () => {
    try {
      const sessionId = getOrCreateSessionId();
      if (sessionId) {
        await postPreferences(sessionId, prefs);
      }
    } catch (err) {
      console.error('[PreferenceStore] API sync failed:', err);
    }
  }, 300);
}

// ─── LocalStorage helpers ───
function loadFromStorage(): Preferences {
  if (typeof window === 'undefined') return DEFAULT_PREFERENCES;
  try {
    const stored = localStorage.getItem(PREFS_STORAGE_KEY);
    if (stored) {
      return { ...DEFAULT_PREFERENCES, ...JSON.parse(stored) };
    }
  } catch {
    // ignore parse errors
  }
  return DEFAULT_PREFERENCES;
}

function saveToStorage(prefs: Preferences) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(prefs));
}

// ─── Store Definition ───
interface PreferenceState {
  preferences: Preferences;
  hydrated: boolean;
  hydrate: () => void;
  toggleRecommend: () => void;
  setPartySize: (size: number) => void;
  togglePriceFilter: () => void;
  setPriceRange: (range: PriceRange) => void;
  setPreferences: (prefs: Preferences) => void;
}

export const usePreferenceStore = create<PreferenceState>((set, get) => ({
  preferences: DEFAULT_PREFERENCES,
  hydrated: false,

  hydrate: () => {
    const loaded = loadFromStorage();
    set({ preferences: loaded, hydrated: true });
  },

  toggleRecommend: () => {
    const current = get().preferences;
    const updated: Preferences = {
      ...current,
      recommendEnabled: !current.recommendEnabled,
    };
    saveToStorage(updated);
    debouncedSync(updated);
    set({ preferences: updated });
  },

  setPartySize: (size: number) => {
    const clamped = Math.min(10, Math.max(1, size));
    const current = get().preferences;
    const updated: Preferences = { ...current, partySize: clamped };
    saveToStorage(updated);
    debouncedSync(updated);
    set({ preferences: updated });
  },

  togglePriceFilter: () => {
    const current = get().preferences;
    const updated: Preferences = {
      ...current,
      priceFilterEnabled: !current.priceFilterEnabled,
    };
    saveToStorage(updated);
    debouncedSync(updated);
    set({ preferences: updated });
  },

  setPriceRange: (range: PriceRange) => {
    const clampedMin = Math.max(20000, Math.min(range.min, range.max));
    const clampedMax = Math.min(100000, Math.max(range.min, range.max));
    const current = get().preferences;
    const updated: Preferences = {
      ...current,
      priceRange: { min: clampedMin, max: clampedMax },
    };
    saveToStorage(updated);
    debouncedSync(updated);
    set({ preferences: updated });
  },

  setPreferences: (prefs: Preferences) => {
    saveToStorage(prefs);
    set({ preferences: prefs });
  },
}));
