'use client';

import { useSeatStore } from '@/stores/useSeatStore';

const REASON_LABELS: Record<string, string> = {
  HELD_BY_OTHERS: '이 좌석은 다른 사용자가 이미 선점하였습니다.',
  ALREADY_HAS_ACTIVE_HOLD: '이미 선점 중인 좌석이 있습니다.',
  SOLD_OUT: '해당 좌석이 매진되었습니다.',
  NETWORK_ERROR: '네트워크 오류가 발생했습니다.',
  MISSING_IDEMPOTENCY_KEY: '요청 오류가 발생했습니다.',
};

export default function HoldFailureModal() {
  const { modalOpen, holdResult, closeModal } = useSeatStore();

  if (!modalOpen || !holdResult) return null;

  const reasonText = holdResult.reason
    ? REASON_LABELS[holdResult.reason] || holdResult.reason
    : '좌석 선점에 실패했습니다.';

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-sm mx-4 rounded-2xl bg-white dark:bg-zinc-900 shadow-2xl overflow-hidden">
        {/* Red accent */}
        <div className="h-1.5 bg-gradient-to-r from-rose-500 to-red-500" />

        <div className="p-6 space-y-4">
          {/* Icon */}
          <div className="flex justify-center">
            <div className="w-14 h-14 rounded-full bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center">
              <span className="text-3xl">❌</span>
            </div>
          </div>

          {/* Message */}
          <div className="text-center space-y-2">
            <h3 className="text-lg font-bold text-zinc-900 dark:text-white">
              선점 실패
            </h3>
            <p className="text-sm text-zinc-600 dark:text-zinc-400" data-testid="hold-fail-reason">
              {reasonText}
            </p>
          </div>

          {/* Close Button */}
          <button
            onClick={closeModal}
            className="w-full py-3 rounded-xl font-semibold bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 hover:opacity-90 transition-all"
            data-testid="hold-fail-close"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
