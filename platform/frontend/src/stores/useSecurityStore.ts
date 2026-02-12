'use client';

import { create } from 'zustand';
import { getOrCreateSessionId } from '@/services/api';

interface ChallengeData {
  challengeId: string;
  prompt: string;
  type: string;
  imageUrl?: string | null;
}

type SecurityStatus = 'IDLE' | 'LOADING' | 'SUBMITTING' | 'FAILED';

interface SecurityState {
  isVisible: boolean;
  challengeData: ChallengeData | null;
  status: SecurityStatus;
  errorMessage: string | null;
  remainingAttempts: number;

  showChallenge: () => Promise<void>;
  hideChallenge: () => void;
  submitAnswer: (answer: string) => Promise<boolean>;
}

export const useSecurityStore = create<SecurityState>((set, get) => ({
  isVisible: false,
  challengeData: null,
  status: 'IDLE',
  errorMessage: null,
  remainingAttempts: 3,

  showChallenge: async () => {
    set({ isVisible: true, status: 'LOADING', errorMessage: null });

    try {
      const sessionId = getOrCreateSessionId();
      const res = await fetch(`/api/security/challenge?sessionId=${sessionId}`);
      if (!res.ok) throw new Error('Failed to fetch challenge');

      const data: ChallengeData = await res.json();
      set({ challengeData: data, status: 'IDLE' });
    } catch (err) {
      console.error('[SecurityStore] Failed to fetch challenge:', err);
      set({ status: 'IDLE', errorMessage: '보안 문제를 불러올 수 없습니다.' });
    }
  },

  hideChallenge: () => {
    set({
      isVisible: false,
      challengeData: null,
      status: 'IDLE',
      errorMessage: null,
    });
  },

  submitAnswer: async (answer: string) => {
    const { challengeData } = get();
    if (!challengeData) return false;

    set({ status: 'SUBMITTING', errorMessage: null });

    try {
      const sessionId = getOrCreateSessionId();
      const res = await fetch('/api/security/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          challengeId: challengeData.challengeId,
          answer,
          sessionId,
        }),
      });

      if (!res.ok) throw new Error('Verify request failed');

      const data = await res.json();

      if (data.result === 'PASS') {
        set({
          isVisible: false,
          challengeData: null,
          status: 'IDLE',
          errorMessage: null,
          remainingAttempts: 3,
        });
        return true;
      } else {
        set({
          status: 'FAILED',
          errorMessage: `오답입니다. 남은 기회: ${data.remainingAttempts}회`,
          remainingAttempts: data.remainingAttempts,
        });
        return false;
      }
    } catch (err) {
      console.error('[SecurityStore] Verify failed:', err);
      set({ status: 'FAILED', errorMessage: '검증 요청에 실패했습니다.' });
      return false;
    }
  },
}));
