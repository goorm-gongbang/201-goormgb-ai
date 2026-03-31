/**
 * Stage 7: Client-side event tracker with batching.
 * Events are queued and sent to POST /api/logs every 1 second or when batch reaches 5 events.
 */

interface TrackEvent {
  sessionId: string;
  eventType: string;
  requestId?: string;
  correlationId?: string;
  payload?: Record<string, unknown>;
}

const BATCH_SIZE = 5;
const FLUSH_INTERVAL_MS = 1000;

let eventQueue: TrackEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function getSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  return localStorage.getItem('tm_session_id') || 'anonymous';
}

function getCorrelationId(): string {
  if (typeof window === 'undefined') return '';
  return sessionStorage.getItem('correlationId') || '';
}

/**
 * Track a client-side event. Adds to batch queue.
 */
export function trackEvent(eventType: string, payload?: Record<string, unknown>): void {
  if (typeof window === 'undefined') return;

  const event: TrackEvent = {
    sessionId: getSessionId(),
    eventType,
    requestId: crypto.randomUUID(),
    correlationId: getCorrelationId(),
    payload: { ...payload, clientTs: new Date().toISOString() },
  };

  eventQueue.push(event);

  // Flush if batch size reached
  if (eventQueue.length >= BATCH_SIZE) {
    flush();
  } else if (!flushTimer) {
    // Schedule flush after interval
    flushTimer = setTimeout(flush, FLUSH_INTERVAL_MS);
  }
}

/**
 * Flush queued events to the server.
 */
async function flush(): Promise<void> {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }

  if (eventQueue.length === 0) return;

  const batch = [...eventQueue];
  eventQueue = [];

  try {
    await fetch('/api/logs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(batch),
    });
  } catch (err) {
    // Silent fail — re-queue on error
    console.warn('[EventTracker] Flush failed, re-queuing', err);
    eventQueue.unshift(...batch);
  }
}

// Flush on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (eventQueue.length > 0) {
      navigator.sendBeacon('/api/logs', JSON.stringify(eventQueue));
    }
  });
}

export default trackEvent;
