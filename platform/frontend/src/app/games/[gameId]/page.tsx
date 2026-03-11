'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { getGame, postBookingEntry, postQueueEnter, getOrCreateSessionId, resetSessionId } from '@/services/api';
import { usePreferenceStore } from '@/stores/usePreferenceStore';
import BookingCard from '@/components/BookingCard';
import GameInfoTabs from '@/components/GameInfoTabs';
import type { GameDetail } from '@/types';

export default function GameDetailPage() {
  const params = useParams<{ gameId: string }>();
  const router = useRouter();
  const gameId = params.gameId;

  const [game, setGame] = useState<GameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [bookingLoading, setBookingLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { preferences, hydrate, hydrated } = usePreferenceStore();

  // Hydrate preferences from localStorage on mount
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Ensure session ID exists and fetch game data
  useEffect(() => {
    if (!gameId) return;

    async function fetchGame() {
      try {
        setLoading(true);
        getOrCreateSessionId(); // ensure session exists
        const data = await getGame(gameId);
        setGame(data);
      } catch (err) {
        console.error('[GameDetailPage] Failed to fetch game:', err);
        setError('경기 정보를 불러올 수 없습니다.');
      } finally {
        setLoading(false);
      }
    }

    fetchGame();
  }, [gameId]);

  // Handle booking click — ALWAYS enters queue.
  // recommendEnabled determines seat selection UI mode (RECOMMEND vs MAP), not queue bypass.
  const handleBookingClick = async () => {
    if (!game || !hydrated) return;

    try {
      setBookingLoading(true);
      const sessionId = resetSessionId();

      const queueResponse = await postQueueEnter({
        sessionId,
        gameId: game.gameId,
        mode: preferences.recommendEnabled ? 'RECOMMEND' : 'MAP',
      });
      router.push(`/queue/${queueResponse.queueTicketId}`);
    } catch (err) {
      console.error('[GameDetailPage] Booking failed:', err);
      setError('예매 진입에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setBookingLoading(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-3 border-emerald-500 border-t-transparent" />
          <p className="text-sm text-zinc-500">경기 정보를 불러오는 중...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !game) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950">
        <div className="text-center space-y-3">
          <p className="text-4xl">⚠️</p>
          <p className="text-zinc-600 dark:text-zinc-400">{error || '경기를 찾을 수 없습니다.'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-bold text-zinc-900 dark:text-white">
            🎫 Traffic-Master
          </h1>
          <span className="text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 font-medium">
            Stage 1 · PRE_ENTRY
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Game Info (2/3 width) */}
          <div className="lg:col-span-2">
            <div className="rounded-2xl border border-zinc-200 bg-white shadow-lg p-6 dark:bg-zinc-900 dark:border-zinc-700">
              <GameInfoTabs game={game} />
            </div>
          </div>

          {/* Right: Booking Panel (1/3 width) */}
          <div className="lg:col-span-1">
            <div className="lg:sticky lg:top-20">
              <BookingCard
                saleStatus={game.saleStatus}
                onBookingClick={handleBookingClick}
                loading={bookingLoading}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
