'use client';

import { useEffect } from 'react';
import { useSeatStore, type SeatBundle } from '@/stores/useSeatStore';

interface RecommendPanelProps {
  gameId: string;
}

const TAB_LABELS: Record<string, string> = {
  rank1: '1순위',
  rank2: '2순위',
  rank3: '3순위',
  all: '전체',
};

const RANK_COLORS: Record<number, string> = {
  1: 'bg-emerald-500',
  2: 'bg-blue-500',
  3: 'bg-amber-500',
};

export default function RecommendPanel({ gameId }: RecommendPanelProps) {
  const {
    recommendations,
    selectedRecommendation,
    activeTab,
    partySize,
    holdSubmitting,
    setActiveTab,
    setRecommendations,
    selectRecommendation,
    submitHold,
    setPartySize,
  } = useSeatStore();

  // Fetch recommendations on tab/partySize change
  useEffect(() => {
    async function fetchRecs() {
      try {
        const res = await fetch(
          `/api/recommendations?gameId=${gameId}&partySize=${partySize}&tab=${activeTab}`
        );
        if (res.ok) {
          const data: SeatBundle[] = await res.json();
          setRecommendations(data);
        }
      } catch (err) {
        console.error('[RecommendPanel] Fetch failed:', err);
      }
    }
    fetchRecs();
  }, [gameId, partySize, activeTab, setRecommendations]);

  const handleAutoSelect = async () => {
    if (recommendations.length > 0) {
      const result = await submitHold(recommendations[0]);
      if (result.status === 'SUCCESS' && result.holdId) {
        // Create order and navigate
        const orderRes = await fetch('/api/orders', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ holdId: result.holdId }),
        });
        const order = await orderRes.json();
        if (order.orderId) {
          window.location.href = `/payment?orderId=${order.orderId}`;
        }
      }
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-zinc-900 dark:text-white">
          사용자 선호 좌석 추천
        </h3>
        <div className="flex items-center gap-2">
          <label className="text-sm text-zinc-500">인원 수</label>
          <select
            value={partySize}
            onChange={(e) => setPartySize(Number(e.target.value))}
            className="px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm"
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Rank Tabs */}
      <div className="flex items-center gap-2">
        {['rank1', 'rank2', 'rank3', 'all'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
              activeTab === tab
                ? 'bg-emerald-500 text-white shadow-md'
                : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200'
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
        <button
          onClick={() => setActiveTab(activeTab)}
          className="ml-auto p-1.5 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          title="새로고침"
        >
          🔄
        </button>
      </div>

      {/* Recommendation Cards */}
      <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
        {recommendations.length === 0 ? (
          <p className="text-center text-sm text-zinc-400 py-8">추천 좌석이 없습니다.</p>
        ) : (
          recommendations.map((bundle) => {
            const isSelected = selectedRecommendation?.seatBundleId === bundle.seatBundleId;
            return (
              <button
                key={bundle.seatBundleId}
                onClick={() => selectRecommendation(bundle)}
                className={`w-full text-left p-4 rounded-xl border-2 transition-all ${
                  isSelected
                    ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20 shadow-md'
                    : 'border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:border-zinc-300'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs text-white px-2 py-0.5 rounded-full font-medium ${RANK_COLORS[bundle.rank] || 'bg-zinc-500'}`}>
                        {bundle.rank}순위
                      </span>
                      <span className="font-bold text-zinc-900 dark:text-white">
                        총 {bundle.totalPrice.toLocaleString()}원
                      </span>
                    </div>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      {bundle.sectionLabel} {bundle.rowLabel}
                    </p>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {bundle.seatIds.map((id) => (
                        <span key={id} className="text-xs px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-700 text-zinc-600 dark:text-zinc-400">
                          #{id.split('-').pop()}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="text-sm text-zinc-400">
                    {(bundle.totalPrice / bundle.seatIds.length).toLocaleString()}원/매
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3 pt-2">
        <button
          onClick={handleAutoSelect}
          disabled={holdSubmitting || recommendations.length === 0}
          className="flex-1 py-3 rounded-xl font-semibold border-2 border-emerald-500 text-emerald-600 hover:bg-emerald-50 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          자동 선택
        </button>
        <button
          id="booking-button-s5"
          onClick={async () => {
            if (!selectedRecommendation) return;
            const result = await submitHold();
            if (result.status === 'SUCCESS' && result.holdId) {
              const orderRes = await fetch('/api/orders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ holdId: result.holdId }),
              });
              const order = await orderRes.json();
              if (order.orderId) {
              window.location.href = `/payment?orderId=${order.orderId}`;
              }
            }
          }}
          disabled={holdSubmitting || !selectedRecommendation}
          className="flex-1 py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg"
        >
          {holdSubmitting ? '처리 중...' : '예매하기'}
        </button>
      </div>
    </div>
  );
}
