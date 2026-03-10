/**
 * Stage 7: API Client wrapper with Correlation ID, Test Mode headers, and error handling.
 */

const API_BASE = '/api';

import { HTTP_HEADERS, REASON_CODES, SESSION_STORAGE_KEYS, STORAGE_KEYS } from '@/contracts/http';
import { useSecurityStore } from '@/stores/useSecurityStore';
import { redirectToTerminal } from '@/services/terminal';

// ─── Correlation ID Management ───

function getCorrelationId(): string {
  if (typeof window === 'undefined') return crypto.randomUUID();
  let id = sessionStorage.getItem(SESSION_STORAGE_KEYS.CORRELATION_ID);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_STORAGE_KEYS.CORRELATION_ID, id);
  }
  return id;
}

function getSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  // Must match the key used in api.ts (TM_SESSION_ID) for consistency
  let sid = localStorage.getItem(STORAGE_KEYS.TM_SESSION_ID);
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEYS.TM_SESSION_ID, sid);
  }
  return sid;
}

// ─── Test Mode Headers ───

function getTestHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const headers: Record<string, string> = {};

  const testMode = localStorage.getItem(STORAGE_KEYS.TM_TEST_MODE);
  if (testMode === 'true') {
    headers[HTTP_HEADERS.X_TM_TEST_MODE] = 'true';

    const holdFail = localStorage.getItem(STORAGE_KEYS.TM_HOLD_FAIL_RATE);
    if (holdFail) headers[HTTP_HEADERS.X_TM_HOLD_FAIL_RATE] = holdFail;

    const payFail = localStorage.getItem(STORAGE_KEYS.TM_PAY_FAIL_RATE);
    if (payFail) headers[HTTP_HEADERS.X_TM_PAYMENT_FAIL_RATE] = payFail;

    const queueWait = localStorage.getItem(STORAGE_KEYS.TM_QUEUE_WAIT_MS);
    if (queueWait) headers[HTTP_HEADERS.X_TM_QUEUE_WAIT_MS] = queueWait;

    const forceChallenge = localStorage.getItem(STORAGE_KEYS.TM_FORCE_CHALLENGE);
    if (forceChallenge) headers[HTTP_HEADERS.X_TM_FORCE_CHALLENGE] = forceChallenge;
  }

  return headers;
}

// ─── Error Type ───

export interface AppError {
  status: 'FAIL';
  reasonCode: string;
  message: string;
  httpStatus: number;
}

function isAppError(data: unknown): data is { status: string; reasonCode: string; message: string } {
  return typeof data === 'object' && data !== null && 'reasonCode' in data;
}

// ─── Core Request Function ───

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  idempotencyKey?: string;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, idempotencyKey } = options;

  const mergedHeaders: Record<string, string> = {
    [HTTP_HEADERS.CONTENT_TYPE]: HTTP_HEADERS.APPLICATION_JSON,
    [HTTP_HEADERS.X_CORRELATION_ID]: getCorrelationId(),
    [HTTP_HEADERS.X_SESSION_ID]: getSessionId(),
    ...getTestHeaders(),
    ...headers,
  };

  if (idempotencyKey) {
    mergedHeaders[HTTP_HEADERS.IDEMPOTENCY_KEY] = idempotencyKey;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: mergedHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    if (data && isAppError(data)) {
      if (data.reasonCode === REASON_CODES.BLOCKED) {
        const secState = useSecurityStore.getState();
        secState.hideChallenge();
        redirectToTerminal({
          reasonCode: data.reasonCode,
          httpStatus: res.status,
          message: data.message,
        });
      } else if (data.reasonCode === REASON_CODES.CHALLENGE_REQUIRED) {
        // Global Security Challenge Trigger — only if modal is not already showing
        const secState = useSecurityStore.getState();
        if (!secState.isVisible) secState.showChallenge();
      }
      
      const err: AppError = {
        status: 'FAIL',
        reasonCode: data.reasonCode,
        message: data.message,
        httpStatus: res.status,
      };
      throw err;
    }
    throw { status: 'FAIL', reasonCode: 'UNKNOWN', message: 'Request failed', httpStatus: res.status } as AppError;
  }

  return data as T;
}

// ─── Convenience Methods ───

export const api = {
  get: <T>(path: string) => apiRequest<T>(path),

  post: <T>(path: string, body: unknown, idempotencyKey?: string) =>
    apiRequest<T>(path, { method: 'POST', body, idempotencyKey }),

  patch: <T>(path: string, body: unknown) =>
    apiRequest<T>(path, { method: 'PATCH', body }),

  delete: <T>(path: string) =>
    apiRequest<T>(path, { method: 'DELETE' }),
};

export default api;
