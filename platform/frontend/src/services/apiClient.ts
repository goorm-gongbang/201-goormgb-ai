/**
 * Stage 7: API Client wrapper with Correlation ID, Test Mode headers, and error handling.
 */

const API_BASE = '/api';

// ─── Correlation ID Management ───

function getCorrelationId(): string {
  if (typeof window === 'undefined') return crypto.randomUUID();
  let id = sessionStorage.getItem('correlationId');
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem('correlationId', id);
  }
  return id;
}

function getSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  return localStorage.getItem('tm_session_id') || 'anonymous';
}

// ─── Test Mode Headers ───

function getTestHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const headers: Record<string, string> = {};

  const testMode = localStorage.getItem('tm_test_mode');
  if (testMode === 'true') {
    headers['X-TM-TestMode'] = 'true';

    const holdFail = localStorage.getItem('tm_hold_fail_rate');
    if (holdFail) headers['X-TM-HoldFailRate'] = holdFail;

    const payFail = localStorage.getItem('tm_pay_fail_rate');
    if (payFail) headers['X-TM-PaymentFailRate'] = payFail;

    const queueWait = localStorage.getItem('tm_queue_wait_ms');
    if (queueWait) headers['X-TM-QueueWaitMs'] = queueWait;

    const forceChallenge = localStorage.getItem('tm_force_challenge');
    if (forceChallenge) headers['X-TM-ForceChallenge'] = forceChallenge;
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
    'Content-Type': 'application/json',
    'X-Correlation-Id': getCorrelationId(),
    'X-Session-Id': getSessionId(),
    ...getTestHeaders(),
    ...headers,
  };

  if (idempotencyKey) {
    mergedHeaders['Idempotency-Key'] = idempotencyKey;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: mergedHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    if (data && isAppError(data)) {
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
