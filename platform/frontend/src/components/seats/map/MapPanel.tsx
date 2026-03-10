'use client';

import { useSeatStore } from '@/stores/useSeatStore';
import { API_PATHS, HTTP_HEADERS } from '@/contracts/http';
import ZoneList from './ZoneList';
import { getOrCreateSessionId } from '@/services/api';

interface MapPanelProps {
  gameId: string;
}

export default function MapPanel({ gameId }: MapPanelProps) {
  const {
    selectedSeats,
    partySize,
    holdSubmitting,
    submitMapHold,
    setPartySize,
  } = useSeatStore();

  const canBook = selectedSeats.length === partySize;

  const handleBook = async () => {
    const result = await submitMapHold();
    if (result.status === 'SUCCESS' && result.holdId) {
      const orderRes = await fetch(API_PATHS.ORDERS, {
        method: 'POST',
        headers: {
          [HTTP_HEADERS.CONTENT_TYPE]: HTTP_HEADERS.APPLICATION_JSON,
          [HTTP_HEADERS.X_SESSION_ID]: getOrCreateSessionId(),
        },
        body: JSON.stringify({ holdId: result.holdId }),
      });
      const order = await orderRes.json();
      if (order.orderId) {
        window.location.href = `/payment?orderId=${order.orderId}`;
      }
    }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-zinc-900 dark:text-white">
          🗺️ 맵 모드
        </h3>
        <div className="flex items-center gap-2">
          <label className="text-sm text-zinc-500">인원 수</label>
          <select
            value={partySize}
            onChange={(e) => setPartySize(Number(e.target.value))}
            className="px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm"
            data-testid="party-size-select"
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Zone List */}
      <ZoneList gameId={gameId} />

      {/* Selected Seats Table */}
      {selectedSeats.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-bold text-zinc-700 dark:text-zinc-300">
            선택한 좌석 ({selectedSeats.length}/{partySize})
          </h4>
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-700">
            {selectedSeats.map((seat, i) => (
              <div key={seat.seatId} className="flex items-center justify-between px-4 py-2">
                <span className="text-sm text-zinc-700 dark:text-zinc-300">
                  <span className="text-emerald-500 font-bold mr-2">#{i + 1}</span>
                  {seat.label}
                </span>
                <span className="text-xs text-zinc-400 font-mono">{seat.seatId}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Booking Button */}
      <button
        id="booking-button-map"
        data-testid="map-booking-button"
        onClick={handleBook}
        disabled={!canBook || holdSubmitting}
        className={`w-full py-3 rounded-xl font-semibold transition-all shadow-lg ${
          canBook
            ? 'text-white bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700'
            : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-400 cursor-not-allowed'
        }`}
      >
        {holdSubmitting
          ? '처리 중...'
          : canBook
          ? `예매하기 (${selectedSeats.length}석)`
          : `좌석 ${partySize - selectedSeats.length}석 더 선택해주세요`
        }
      </button>
    </div>
  );
}
