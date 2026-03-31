'use client';

import { create } from 'zustand';
import { STORAGE_KEYS } from '@/contracts/http';
import { getOrCreateSessionId } from '@/services/api';
import { redirectToTerminal } from '@/services/terminal';

interface ChallengeData {
  challengeId: string;
  prompt: string;
  type: string;
  imageUrl?: string | null;
  challengeToken?: string;
  issuedAt?: number;
  expiresAt?: number;
  attemptLimit?: number;
}

type SecurityStatus = 'IDLE' | 'LOADING' | 'SUBMITTING' | 'FAILED';
type CatchBallTelemetry = Record<string, unknown>;

function normalizeCatchBallTelemetry(
  telemetry: CatchBallTelemetry | undefined,
  challengeId: string,
  sessionId: string,
  issuedAt?: number,
): CatchBallTelemetry | null {
  if (!telemetry || typeof telemetry !== 'object') return null;
  const normalized: CatchBallTelemetry = { ...telemetry };
  normalized.challenge_id = challengeId;
  normalized.session_id = sessionId;
  if (typeof issuedAt === 'number' && Number.isFinite(issuedAt)) {
    normalized.issued_at = issuedAt;
  }
  return normalized;
}

interface SecurityState {
  isVisible: boolean;
  challengeData: ChallengeData | null;
  status: SecurityStatus;
  errorMessage: string | null;
  remainingAttempts: number;
  lastResult: 'PASS' | 'FAIL' | null;

  showChallenge: () => Promise<void>;
  hideChallenge: () => void;
  submitAnswer: (answer: string, telemetry?: CatchBallTelemetry) => Promise<boolean>;
}

export const useSecurityStore = create<SecurityState>((set, get) => ({
  isVisible: false,
  challengeData: null,
  status: 'IDLE',
  errorMessage: null,
  remainingAttempts: 3,

  lastResult: null,

  showChallenge: async () => {
    set({ isVisible: true, status: 'LOADING', errorMessage: null, lastResult: null });

    try {
      const sessionId = getOrCreateSessionId();
      const res = await fetch(`/api/security/challenge?sessionId=${sessionId}`);
      if (!res.ok) throw new Error('Failed to fetch challenge');

      const data: ChallengeData = await res.json();
      set({
        challengeData: data,
        status: 'IDLE',
        remainingAttempts: data.attemptLimit ?? 2,
      });
    } catch (err) {
      console.error('[SecurityStore] Failed to fetch challenge:', err);
      set({ status: 'IDLE', errorMessage: '보안 문제를 불러올 수 없습니다.', lastResult: 'FAIL' });
    }
  },

  hideChallenge: () => {
    set({
      isVisible: false,
      challengeData: null,
      status: 'IDLE',
      errorMessage: null,
      // Do not reset lastResult here so callers can read it
    });
  },

  submitAnswer: async (answer: string, telemetry?: CatchBallTelemetry) => {
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
          challengeToken: challengeData.challengeToken ?? '',
          telemetry: normalizeCatchBallTelemetry(
            telemetry,
            challengeData.challengeId,
            sessionId,
            challengeData.issuedAt,
          ),
        }),
      });

      if (!res.ok) throw new Error('Verify request failed');

      const data = await res.json();

      if (data.result === 'PASS') {
        try {
          localStorage.setItem(STORAGE_KEYS.TM_VQA_PASSED_SESSION_ID, sessionId);
          // Legacy key cleanup
          localStorage.removeItem('TM_VQA_PASSED_ONCE');
        } catch {}
        set({
          isVisible: false,
          challengeData: null,
          status: 'IDLE',
          errorMessage: null,
          remainingAttempts: 3,
          lastResult: 'PASS',
        });
        return true;
      } else {
        if (data.reasonCode === 'BLOCKED') {
          set({
            isVisible: false,
            challengeData: null,
            status: 'IDLE',
            errorMessage: null,
            lastResult: 'FAIL',
          });
          redirectToTerminal({
            reasonCode: data.reasonCode,
            httpStatus: 403,
            message: data.message ?? '요청이 차단되었습니다.',
          });
          return false;
        }
        const reason = data.reasonCode ? ` (${data.reasonCode})` : '';
        set({
          status: 'FAILED',
          errorMessage: `검증 실패${reason}. 남은 기회: ${data.remainingAttempts}회`,
          remainingAttempts: data.remainingAttempts,
          lastResult: 'FAIL',
        });
        return false;
      }
    } catch (err) {
      console.error('[SecurityStore] Verify failed:', err);
      set({ status: 'FAILED', errorMessage: '검증 요청에 실패했습니다.', lastResult: 'FAIL' });
      return false;
    }
  },
}));
