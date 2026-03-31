'use client';

import { SESSION_STORAGE_KEYS } from '@/contracts/http';

export interface TerminalRedirectPayload {
  reasonCode: string;
  httpStatus?: number;
  message?: string;
}

export function redirectToTerminal(payload: TerminalRedirectPayload): void {
  if (typeof window === 'undefined') return;

  const { reasonCode, httpStatus, message } = payload;

  try {
    sessionStorage.setItem(SESSION_STORAGE_KEYS.TERMINAL_REASON, reasonCode);
    if (typeof httpStatus === 'number' && Number.isFinite(httpStatus)) {
      sessionStorage.setItem(SESSION_STORAGE_KEYS.TERMINAL_HTTP_STATUS, String(httpStatus));
    } else {
      sessionStorage.removeItem(SESSION_STORAGE_KEYS.TERMINAL_HTTP_STATUS);
    }
    if (message && message.trim()) {
      sessionStorage.setItem(SESSION_STORAGE_KEYS.TERMINAL_MESSAGE, message.trim());
    } else {
      sessionStorage.removeItem(SESSION_STORAGE_KEYS.TERMINAL_MESSAGE);
    }
  } catch {
    // Ignore storage failures; URL still carries terminal reason.
  }

  const params = new URLSearchParams({ reasonCode });
  if (typeof httpStatus === 'number' && Number.isFinite(httpStatus)) {
    params.set('httpStatus', String(httpStatus));
  }

  window.location.assign(`/terminal?${params.toString()}`);
}
