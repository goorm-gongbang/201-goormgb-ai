'use client';

import { useParams, useRouter } from 'next/navigation';
import { useQueuePolling } from '@/hooks/useQueuePolling';
import QueueOverlay from '@/components/QueueOverlay';

export default function QueuePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const ticketId = params.id;

  const { ticket, error, isPolling } = useQueuePolling({
    ticketId,
    intervalMs: 1000,
    onGranted: (nextUrl) => {
      // Short delay to show "입장 준비 완료!" state
      setTimeout(() => {
        router.push(nextUrl);
      }, 1500);
    },
  });

  // Error state
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="text-center space-y-3">
          <p className="text-4xl">⚠️</p>
          <p className="text-zinc-400">{error}</p>
          <button
            onClick={() => router.push('/')}
            className="text-sm text-emerald-500 hover:underline"
          >
            처음으로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  // Loading state (before first poll)
  if (!ticket) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-3 border-emerald-500 border-t-transparent" />
          <p className="text-sm text-zinc-500">대기열 정보 확인 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      <QueueOverlay
        position={ticket.position}
        progress={ticket.progress}
        status={ticket.status}
        estimatedWaitMs={ticket.estimatedWaitMs}
      />
    </div>
  );
}
