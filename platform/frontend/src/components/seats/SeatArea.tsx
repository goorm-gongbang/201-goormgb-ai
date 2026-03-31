'use client';

import { useSeatStore } from '@/stores/useSeatStore';

/**
 * Stage 4/5: 10x10 seat grid MVP.
 * Highlights seats from the selected SeatBundle.
 */
export default function SeatArea() {
  const selectedRecommendation = useSeatStore((s) => s.selectedRecommendation);

  const selectedSeatIds = new Set(selectedRecommendation?.seatIds || []);

  // Generate 10x10 grid labels
  const rows = Array.from({ length: 10 }, (_, r) => String.fromCharCode(65 + r)); // A-J
  const cols = Array.from({ length: 10 }, (_, c) => c + 1);

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-bold text-zinc-900 dark:text-white">
        🏟️ 좌석 배치도
      </h3>

      {/* Stage indicator */}
      <div className="text-center">
        <div className="inline-block px-8 py-2 rounded-b-xl bg-gradient-to-r from-emerald-400 to-teal-500 text-white text-sm font-bold shadow-md">
          ⚾ FIELD
        </div>
      </div>

      {/* Seat Grid */}
      <div className="bg-white dark:bg-zinc-800 rounded-2xl p-4 border border-zinc-200 dark:border-zinc-700">
        {/* Column headers */}
        <div className="flex gap-1 mb-1 pl-8">
          {cols.map((c) => (
            <div key={c} className="w-8 h-6 flex items-center justify-center text-xs text-zinc-400 font-medium">
              {c}
            </div>
          ))}
        </div>

        {/* Rows */}
        {rows.map((row) => (
          <div key={row} className="flex gap-1 mb-1">
            {/* Row label */}
            <div className="w-6 h-8 flex items-center justify-center text-xs text-zinc-400 font-medium mr-1">
              {row}
            </div>

            {/* Seats */}
            {cols.map((col) => {
              const seatId = `${row}-${col}`;
              const isHighlighted = selectedSeatIds.has(seatId) ||
                // Also check if any selectedSeatId ends with same pattern
                Array.from(selectedSeatIds).some(sid => sid.includes(`${col}번`));

              return (
                <div
                  key={seatId}
                  className={`w-8 h-8 rounded-md flex items-center justify-center text-xs font-medium cursor-default transition-all duration-300 ${
                    isHighlighted
                      ? 'bg-emerald-500 text-white shadow-lg scale-110 ring-2 ring-emerald-300'
                      : 'bg-zinc-100 dark:bg-zinc-700 text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-600'
                  }`}
                  title={seatId}
                >
                  {isHighlighted ? '✓' : '·'}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Selection Info */}
      {selectedRecommendation && (
        <div className="rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 p-3">
          <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
            선택: {selectedRecommendation.sectionLabel} · {selectedRecommendation.rowLabel}
          </p>
          <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
            {selectedRecommendation.seatIds.join(', ')} — 총 {selectedRecommendation.totalPrice.toLocaleString()}원
          </p>
        </div>
      )}
    </div>
  );
}
