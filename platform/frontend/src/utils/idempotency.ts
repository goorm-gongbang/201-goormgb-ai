/**
 * Stage 7: Idempotency Key generator.
 * Auto-generates UUID v4 keys for POST requests to holds, orders, payments.
 */

const IDEMPOTENT_PATHS = ['/holds', '/orders', '/payments'];

/**
 * Generate a new idempotency key.
 */
export function generateIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Check if a request path requires an idempotency key.
 */
export function requiresIdempotency(path: string): boolean {
  return IDEMPOTENT_PATHS.some((p) => path.includes(p));
}

/**
 * Middleware-style: auto-attach Idempotency-Key for qualifying POST requests.
 * Use with apiClient's post method.
 */
export function withIdempotencyKey(
  path: string,
  method: string
): string | undefined {
  if (method === 'POST' && requiresIdempotency(path)) {
    return generateIdempotencyKey();
  }
  return undefined;
}

export default generateIdempotencyKey;
