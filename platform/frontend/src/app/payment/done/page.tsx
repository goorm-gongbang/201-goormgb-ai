'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

function DoneContent() {
  const searchParams = useSearchParams();
  const orderId = searchParams.get('orderId');

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 flex items-center justify-center">
      <div className="max-w-md w-full mx-4 text-center space-y-6">
        {/* Success Icon */}
        <div className="flex justify-center">
          <div className="w-20 h-20 rounded-full bg-gradient-to-r from-emerald-400 to-teal-500 flex items-center justify-center shadow-xl">
            <span className="text-4xl">✅</span>
          </div>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
            결제가 완료되었습니다!
          </h1>
          <p className="text-sm text-zinc-500">
            예매 번호: <span className="font-mono text-emerald-600">{orderId?.substring(0, 8)}</span>
          </p>
        </div>

        <div className="rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 p-4 text-left space-y-2">
          <p className="text-sm text-emerald-700 dark:text-emerald-400">🏟️ KT vs LG</p>
          <p className="text-sm text-emerald-700 dark:text-emerald-400">📅 2026.03.28(토) 14:00</p>
          <p className="text-sm text-emerald-700 dark:text-emerald-400">📍 잠실 야구장</p>
        </div>

        <button
          onClick={() => { window.location.href = '/'; }}
          className="w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 transition-all shadow-lg"
        >
          홈으로 돌아가기
        </button>
      </div>
    </div>
  );
}

export default function PaymentDonePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="h-8 w-8 animate-spin rounded-full border-3 border-emerald-500 border-t-transparent" />
      </div>
    }>
      <DoneContent />
    </Suspense>
  );
}
