export const STORAGE_KEYS = {
  TM_SESSION_ID: 'TM_SESSION_ID',
  TM_PREFERENCES: 'TM_PREFERENCES',
  TM_CAPTURE_RAW_TRAJ: 'TM_CAPTURE_RAW_TRAJ',
  TM_TRAJ_DATASET_ID: 'TM_TRAJ_DATASET_ID',
  TM_TEST_MODE: 'tm_test_mode',
  TM_HOLD_FAIL_RATE: 'tm_hold_fail_rate',
  TM_PAY_FAIL_RATE: 'tm_pay_fail_rate',
  TM_QUEUE_WAIT_MS: 'tm_queue_wait_ms',
  TM_FORCE_CHALLENGE: 'tm_force_challenge',
} as const;

export const SESSION_STORAGE_KEYS = {
  CORRELATION_ID: 'correlationId',
} as const;

export const HTTP_HEADERS = {
  CONTENT_TYPE: 'Content-Type',
  APPLICATION_JSON: 'application/json',
  X_SESSION_ID: 'X-Session-Id',
  X_CORRELATION_ID: 'X-Correlation-Id',
  IDEMPOTENCY_KEY: 'Idempotency-Key',
  X_TM_TEST_MODE: 'X-TM-TestMode',
  X_TM_HOLD_FAIL_RATE: 'X-TM-HoldFailRate',
  X_TM_PAYMENT_FAIL_RATE: 'X-TM-PaymentFailRate',
  X_TM_QUEUE_WAIT_MS: 'X-TM-QueueWaitMs',
  X_TM_FORCE_CHALLENGE: 'X-TM-ForceChallenge',
} as const;

export const REASON_CODES = {
  BLOCKED: 'BLOCKED',
  CHALLENGE_REQUIRED: 'CHALLENGE_REQUIRED',
  MISSING_IDEMPOTENCY_KEY: 'MISSING_IDEMPOTENCY_KEY',
} as const;

export const API_PATHS = {
  TELEMETRY_BEHAVIOR: '/api/telemetry/behavior',
  HOLDS: '/api/holds',
  ORDERS: '/api/orders',
  PAYMENTS: '/api/payments',
} as const;

