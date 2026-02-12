'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

export interface QueueTicketResponse {
  queueTicketId: string;
  position: number;
  estimatedWaitMs: number;
  status: 'WAITING' | 'GRANTED' | 'BLOCKED' | 'NOT_FOUND';
  progress: number;
  nextUrl?: string;
}

import { useSecurityStore } from '@/stores/useSecurityStore';

interface UseQueuePollingOptions {
  ticketId: string;
  intervalMs?: number;
  onGranted?: (nextUrl: string) => void;
}

interface UseQueuePollingResult {
  ticket: QueueTicketResponse | null;
  error: string | null;
  isPolling: boolean;
}

export function useQueuePolling({
  ticketId,
  intervalMs = 1000,
  onGranted,
}: UseQueuePollingOptions): UseQueuePollingResult {
  const [ticket, setTicket] = useState<QueueTicketResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onGrantedRef = useRef(onGranted);

  // Keep callback ref fresh
  useEffect(() => {
    onGrantedRef.current = onGranted;
  }, [onGranted]);

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`/api/queue/${ticketId}`);
      if (!res.ok) {
        setError('대기열 정보를 불러올 수 없습니다.');
        return;
      }

      const data: QueueTicketResponse = await res.json();
      setTicket(data);
      setError(null);

      // Transition: GRANTED → stop polling and redirect
      if (data.status === 'GRANTED' && data.nextUrl) {
        setIsPolling(false);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        onGrantedRef.current?.(data.nextUrl);
      }
    } catch (err) {
      console.error('[useQueuePolling] Poll failed:', err);
      setError('네트워크 오류가 발생했습니다.');
    }
  }, [ticketId]);

  useEffect(() => {
    if (!ticketId) return;

    // Initial fetch
    poll();

    // Set up interval
    intervalRef.current = setInterval(poll, intervalMs);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [ticketId, intervalMs, poll]);

  return { ticket, error, isPolling };
}
