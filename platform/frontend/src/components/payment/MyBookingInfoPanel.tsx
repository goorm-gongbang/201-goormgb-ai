'use client';

import CountdownTimer from './CountdownTimer';
import { usePaymentStore, useCanSubmit } from '@/stores/usePaymentStore';

interface OrderDetail {
  orderId: string;
  gameTitle: string;
  gameDate: string;
  venue: string;
  seatIds: string[];
  totalPrice: number;
  expiresAt: string;
}

interface MyBookingInfoPanelProps {
  order: OrderDetail;
  onExpired: () => void;
}

export default function MyBookingInfoPanel({ order, onExpired }: MyBookingInfoPanelProps) {
  const { submitting, submitPayment, expired, result } = usePaymentStore();
  const canSubmit = useCanSubmit();

  const handlePay = async () => {
    await submitPayment();
  };

  return (
    <div className="space-y-5">
      {/* Timer */}
      <div className="rounded-xl bg-zinc-50 dark:bg-zinc-800 p-4 text-center">
        <p className="text-xs text-zinc-500 mb-1">결제 남은 시간</p>
        <CountdownTimer expiresAt={order.expiresAt} onExpired={onExpired} />
      </div>

      {/* Game Info */}
      <div className="space-y-2">
        <h4 className="text-sm font-bold text-zinc-700 dark:text-zinc-300">경기 정보</h4>
        <div className="text-sm text-zinc-600 dark:text-zinc-400 space-y-1">
          <p>🏟️ {order.gameTitle}</p>
          <p>📅 {order.gameDate}</p>
          <p>📍 {order.venue}</p>
        </div>
      </div>

      {/* Seat Info */}
      <div className="space-y-2">
        <h4 className="text-sm font-bold text-zinc-700 dark:text-zinc-300">좌석 정보</h4>
        <div className="flex flex-wrap gap-1">
          {order.seatIds.map((id) => (
            <span key={id} className="text-xs px-2 py-1 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
              {id}
            </span>
          ))}
        </div>
      </div>

      {/* Price */}
      <div className="rounded-xl border-2 border-emerald-200 dark:border-emerald-700 p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-600 dark:text-zinc-400">총 결제 금액</span>
          <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
            {order.totalPrice.toLocaleString()}원
          </span>
        </div>
      </div>

      {/* Submit */}
      <button
        id="pay-button"
        onClick={handlePay}
        disabled={!canSubmit || expired}
        className={`w-full py-4 rounded-xl font-bold text-lg transition-all shadow-lg ${
          canSubmit && !expired
            ? 'text-white bg-gradient-to-r from-rose-500 to-pink-600 hover:from-rose-600 hover:to-pink-700'
            : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-400 cursor-not-allowed'
        }`}
      >
        {submitting ? '결제 처리 중...' : expired ? '시간 만료' : `${order.totalPrice.toLocaleString()}원 결제하기`}
      </button>

      {/* Result Toast */}
      {result && result.status === 'FAILED' && (
        <div className="rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3 text-center">
          <p className="text-sm text-red-600 dark:text-red-400">
            결제 실패: {result.reasonCode || '알 수 없는 오류'}
          </p>
        </div>
      )}
    </div>
  );
}
