'use client';

import { useEffect } from 'react';
import { useSeatStore, type SeatCell } from '@/stores/useSeatStore';
import { api } from '@/services/apiClient';
import { useSecurityStore } from '@/stores/useSecurityStore';

/**
 * Stage 5 MAP mode: CSS Grid seat view.
 * Renders rows×cols grid with click-to-select behavior.
 *
 * State rendering rules (Derived State):
 *   HELD_BY_OTHERS / UNAVAILABLE → gray, not clickable
 *   AVAILABLE + in selectedSeats  → green (SELECTED_BY_ME), checkmark
 *   AVAILABLE                     → white, clickable
 */

export default function ZoneSeatGridView() {
  const {
    selectedZoneId,
    seatGrid,
    gridRows,
    gridCols,
    selectedSeats,
    partySize,
    setSeatGrid,
    toggleSeat,
  } = useSeatStore();
  
  const lastResult = useSecurityStore((s) => s.lastResult);

  // Fetch seat grid when zone changes
  useEffect(() => {
    if (!selectedZoneId) return;

    async function fetchGrid() {
      try {
        const data = await api.get<any>(`/zones/${selectedZoneId}/seats?gameId=game-001`);
        setSeatGrid(data.seats, data.rows, data.cols);
      } catch (err) {
        console.error('[ZoneSeatGridView] Fetch failed:', err);
      }
    }
    fetchGrid();
  }, [selectedZoneId, setSeatGrid, lastResult]);

  if (!selectedZoneId) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-zinc-400 space-y-3">
        <span className="text-5xl">🗺️</span>
        <p className="text-sm">좌측에서 구역을 선택해주세요</p>
      </div>
    );
  }

  if (seatGrid.length === 0) {
    return (
      <div className="flex justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-3 border-emerald-500 border-t-transparent" />
      </div>
    );
  }

  const selectedIds = new Set(selectedSeats.map(s => s.seatId));

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-zinc-900 dark:text-white">🗺️ 좌석 배치도</h3>
        <span className="text-xs text-zinc-500">
          선택: {selectedSeats.length}/{partySize}
        </span>
      </div>

      {/* Stage */}
      <div className="text-center">
        <div className="inline-block px-10 py-2 rounded-b-xl bg-gradient-to-r from-blue-500 to-indigo-500 text-white text-sm font-bold shadow-md">
          ⚾ FIELD
        </div>
      </div>

      {/* Grid */}
      <div className="overflow-x-auto">
        <div
          className="inline-grid gap-[3px] p-3 bg-white dark:bg-zinc-800 rounded-2xl border border-zinc-200 dark:border-zinc-700"
          style={{
            gridTemplateColumns: `28px repeat(${gridCols}, 28px)`,
            gridTemplateRows: `24px repeat(${gridRows}, 28px)`,
          }}
        >
          {/* Column headers */}
          <div /> {/* empty corner */}
          {Array.from({ length: gridCols }, (_, c) => (
            <div key={`col-${c}`} className="flex items-center justify-center text-[10px] text-zinc-400 font-medium">
              {c + 1}
            </div>
          ))}

          {/* Rows */}
          {Array.from({ length: gridRows }, (_, r) => (
            <>
              {/* Row label */}
              <div key={`row-${r}`} className="flex items-center justify-center text-[10px] text-zinc-400 font-medium">
                {r + 1}
              </div>

              {/* Seat cells */}
              {Array.from({ length: gridCols }, (_, c) => {
                const idx = r * gridCols + c;
                const seat = seatGrid[idx];
                if (!seat) return <div key={`empty-${r}-${c}`} />;

                const isSelectedByMe = selectedIds.has(seat.seatId);
                const isAvailable = seat.status === 'AVAILABLE';
                const isHeld = seat.status === 'HELD_BY_OTHERS';
                const isUnavailable = seat.status === 'UNAVAILABLE';

                let cellClass = 'rounded-[4px] w-7 h-7 flex items-center justify-center text-[10px] font-medium transition-all duration-150 ';

                if (isSelectedByMe) {
                  cellClass += 'bg-emerald-500 text-white shadow-md scale-110 ring-2 ring-emerald-300 cursor-pointer';
                } else if (isHeld) {
                  cellClass += 'bg-rose-200 dark:bg-rose-900/40 text-rose-400 cursor-not-allowed';
                } else if (isUnavailable) {
                  cellClass += 'bg-zinc-200 dark:bg-zinc-700 text-zinc-400 cursor-not-allowed';
                } else if (isAvailable) {
                  cellClass += 'bg-blue-50 dark:bg-zinc-600 text-zinc-500 hover:bg-blue-100 dark:hover:bg-zinc-500 cursor-pointer hover:scale-105';
                }

                return (
                  <button
                    key={seat.seatId}
                    onClick={() => toggleSeat(seat)}
                    disabled={!isAvailable && !isSelectedByMe}
                    className={cellClass}
                    title={`${seat.label} (${seat.status})`}
                  >
                    {isSelectedByMe ? '✓' : isHeld ? '×' : isUnavailable ? '·' : '○'}
                  </button>
                );
              })}
            </>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-zinc-500">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-blue-50 border border-zinc-300" /> 선택 가능</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-emerald-500" /> 내 선택</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-rose-200" /> 선점됨</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-zinc-200" /> 이용 불가</span>
      </div>
    </div>
  );
}
