'use client';

import { usePreferenceStore } from '@/stores/usePreferenceStore';
import type { SaleStatus } from '@/types';

interface BookingCardProps {
  saleStatus: SaleStatus;
  onBookingClick: () => void;
  loading?: boolean;
}

export default function BookingCard({ saleStatus, onBookingClick, loading }: BookingCardProps) {
  const {
    preferences,
    toggleRecommend,
    setPartySize,
    togglePriceFilter,
    setPriceRange,
  } = usePreferenceStore();

  const isBookable = saleStatus === 'ON_SALE';

  const statusLabel: Record<SaleStatus, { text: string; color: string }> = {
    ON_SALE: { text: '판매중', color: 'bg-emerald-500' },
    SOLD_OUT: { text: '매진', color: 'bg-red-500' },
    CLOSED: { text: '판매종료', color: 'bg-gray-500' },
  };

  const status = statusLabel[saleStatus];

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white shadow-lg p-6 space-y-6 dark:bg-zinc-900 dark:border-zinc-700">
      {/* Sale Status Badge */}
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${status.color}`} />
        <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
          {status.text}
        </span>
      </div>

      {/* ─── Recommend Toggle ─── */}
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
          🎯 좌석 추천
        </label>
        <button
          onClick={toggleRecommend}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            preferences.recommendEnabled
              ? 'bg-emerald-500'
              : 'bg-zinc-300 dark:bg-zinc-600'
          }`}
          aria-label="Toggle recommend"
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              preferences.recommendEnabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>

      {/* ─── Party Size ─── */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
          👥 인원 수
        </label>
        <select
          value={preferences.partySize}
          onChange={(e) => setPartySize(Number(e.target.value))}
          className="w-full rounded-lg border border-zinc-300 bg-white py-2 px-3 text-sm text-zinc-800 dark:bg-zinc-800 dark:border-zinc-600 dark:text-zinc-200 focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none"
        >
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n}명
            </option>
          ))}
        </select>
      </div>

      {/* ─── Price Filter Toggle ─── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
            💰 가격대 필터
          </label>
          <button
            onClick={togglePriceFilter}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              preferences.priceFilterEnabled
                ? 'bg-emerald-500'
                : 'bg-zinc-300 dark:bg-zinc-600'
            }`}
            aria-label="Toggle price filter"
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                preferences.priceFilterEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>

        {/* ─── Price Range Slider ─── */}
        {preferences.priceFilterEnabled && (
          <div className="space-y-2 bg-zinc-50 dark:bg-zinc-800 rounded-lg p-3">
            <div className="flex justify-between text-xs text-zinc-500">
              <span>₩{preferences.priceRange.min.toLocaleString()}</span>
              <span>₩{preferences.priceRange.max.toLocaleString()}</span>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-zinc-500">최소</label>
              <input
                type="range"
                min={20000}
                max={100000}
                step={5000}
                value={preferences.priceRange.min}
                onChange={(e) =>
                  setPriceRange({
                    ...preferences.priceRange,
                    min: Number(e.target.value),
                  })
                }
                className="w-full accent-emerald-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-zinc-500">최대</label>
              <input
                type="range"
                min={20000}
                max={100000}
                step={5000}
                value={preferences.priceRange.max}
                onChange={(e) =>
                  setPriceRange({
                    ...preferences.priceRange,
                    max: Number(e.target.value),
                  })
                }
                className="w-full accent-emerald-500"
              />
            </div>
          </div>
        )}
      </div>

      {/* ─── Booking Button ─── */}
      <button
        id="booking-button"
        onClick={onBookingClick}
        disabled={!isBookable || loading}
        className={`w-full py-3 rounded-xl text-base font-bold shadow transition-all duration-200 ${
          isBookable && !loading
            ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white hover:from-emerald-600 hover:to-teal-700 hover:shadow-lg active:scale-[0.98]'
            : 'bg-zinc-300 text-zinc-500 cursor-not-allowed dark:bg-zinc-700 dark:text-zinc-500'
        }`}
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            처리중...
          </span>
        ) : isBookable ? (
          '🎫 예매하기'
        ) : (
          saleStatus === 'SOLD_OUT' ? '매진되었습니다' : '판매가 종료되었습니다'
        )}
      </button>
    </div>
  );
}
