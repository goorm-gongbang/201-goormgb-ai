'use client';

import { useSearchParams, useRouter } from 'next/navigation';
import { Suspense, useState, useEffect } from 'react';
import RecommendPanel from '@/components/seats/RecommendPanel';
import SeatArea from '@/components/seats/SeatArea';
import MapPanel from '@/components/seats/map/MapPanel';
import ZoneSeatGridView from '@/components/seats/map/ZoneSeatGridView';
import HoldFailureModal from '@/components/common/HoldFailureModal';

function SeatsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const modeParam = searchParams.get('mode') || 'RECOMMEND';
  const gameId = 'game-001';

  const [recommendEnabled, setRecommendEnabled] = useState(modeParam === 'RECOMMEND');
  const isMap = !recommendEnabled;

  // Sync toggle → URL
  useEffect(() => {
    const newMode = recommendEnabled ? 'RECOMMEND' : 'MAP';
    const currentMode = searchParams.get('mode') || 'RECOMMEND';
    if (newMode !== currentMode) {
      router.replace(`/seats?mode=${newMode}`, { scroll: false });
    }
  }, [recommendEnabled, searchParams, router]);

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold text-zinc-900 dark:text-white">
              🎫 Traffic-Master
            </h1>
            <span className="text-xs text-zinc-500">좌석 선택 &gt; 주문서 &gt; 결제하기</span>
          </div>
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${
            isMap
              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
              : 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400'
          }`}>
            {isMap ? '🗺️ MAP 모드' : '⭐ 추천 모드'}
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left: Seat View (3/5) */}
          <div className="lg:col-span-3">
            <div className="rounded-2xl border border-zinc-200 bg-white shadow-lg p-6 dark:bg-zinc-900 dark:border-zinc-700">
              {isMap ? <ZoneSeatGridView /> : <SeatArea />}
            </div>
          </div>

          {/* Right: Control Panel (2/5) */}
          <div className="lg:col-span-2">
            <div className="lg:sticky lg:top-20 space-y-4">
              {/* Recommend Toggle Card */}
              <div className="rounded-2xl border border-zinc-200 bg-white shadow-lg p-5 dark:bg-zinc-900 dark:border-zinc-700">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-zinc-900 dark:text-white">
                    사용자 선호 좌석 추천
                  </span>
                  <button
                    onClick={() => setRecommendEnabled(!recommendEnabled)}
                    className={`relative w-12 h-7 rounded-full transition-colors duration-300 ${
                      recommendEnabled
                        ? 'bg-emerald-500'
                        : 'bg-zinc-300 dark:bg-zinc-600'
                    }`}
                    aria-label="추천 모드 토글"
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow-md transition-transform duration-300 ${
                        recommendEnabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Mode-specific Panel */}
              <div className="rounded-2xl border border-zinc-200 bg-white shadow-lg p-6 dark:bg-zinc-900 dark:border-zinc-700">
                {isMap ? <MapPanel gameId={gameId} /> : <RecommendPanel gameId={gameId} />}
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Hold Failure Modal */}
      <HoldFailureModal />
    </div>
  );
}

export default function SeatsPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="h-8 w-8 animate-spin rounded-full border-3 border-emerald-500 border-t-transparent" />
      </div>
    }>
      <SeatsContent />
    </Suspense>
  );
}
