'use client';

import { create } from 'zustand';
import { getOrCreateSessionId } from '@/services/api';

// ─── Types ───

export interface SeatBundle {
  seatBundleId: string;
  gameId: string;
  seatIds: string[];
  sectionLabel: string;
  rowLabel: string;
  totalPrice: number;
  rank: number;
}

export interface SeatCell {
  seatId: string;
  label: string;
  status: 'AVAILABLE' | 'HELD_BY_OTHERS' | 'UNAVAILABLE';
}

export interface SelectedSeat {
  seatId: string;
  label: string;
}

interface HoldResult {
  holdId?: string;
  status: string;
  reason?: string;
  expiresAt?: string;
}

type ViewMode = 'listView' | 'focusedSeatView';

// ─── Store ───

interface SeatState {
  // Common
  viewMode: ViewMode;
  holdSubmitting: boolean;
  holdResult: HoldResult | null;
  modalOpen: boolean;
  partySize: number;
  gameId: string;

  // Recommend mode
  recommendations: SeatBundle[];
  selectedRecommendation: SeatBundle | null;
  activeTab: string;

  // Map mode
  selectedZoneId: string | null;
  selectedSeats: SelectedSeat[];
  seatGrid: SeatCell[];
  gridRows: number;
  gridCols: number;

  // Common actions
  setGameId: (id: string) => void;
  setPartySize: (size: number) => void;
  closeModal: () => void;
  resetSelection: () => void;

  // Recommend actions
  setActiveTab: (tab: string) => void;
  setRecommendations: (bundles: SeatBundle[]) => void;
  selectRecommendation: (bundle: SeatBundle) => void;
  submitHold: (bundle?: SeatBundle) => Promise<HoldResult>;

  // Map actions
  selectZone: (zoneId: string) => void;
  setSeatGrid: (grid: SeatCell[], rows: number, cols: number) => void;
  toggleSeat: (seat: SeatCell) => void;
  submitMapHold: () => Promise<HoldResult>;
}

export const useSeatStore = create<SeatState>((set, get) => ({
  // Common
  viewMode: 'listView',
  holdSubmitting: false,
  holdResult: null,
  modalOpen: false,
  partySize: 2,
  gameId: 'game-001',

  // Recommend
  recommendations: [],
  selectedRecommendation: null,
  activeTab: 'all',

  // Map
  selectedZoneId: null,
  selectedSeats: [],
  seatGrid: [],
  gridRows: 0,
  gridCols: 0,

  // ─── Common Actions ───

  setGameId: (id) => set({ gameId: id }),
  setPartySize: (size) => set({ partySize: size, selectedSeats: [] }),
  closeModal: () => set({ modalOpen: false, holdResult: null, selectedRecommendation: null, selectedSeats: [], viewMode: 'listView' }),
  resetSelection: () => set({ selectedRecommendation: null, selectedSeats: [], viewMode: 'listView', holdResult: null, modalOpen: false }),

  // ─── Recommend Actions ───

  setActiveTab: (tab) => set({ activeTab: tab }),
  setRecommendations: (bundles) => set({ recommendations: bundles }),
  selectRecommendation: (bundle) => set({ selectedRecommendation: bundle, viewMode: 'focusedSeatView' }),

  submitHold: async (bundle?: SeatBundle) => {
    const state = get();
    const target = bundle || state.selectedRecommendation;
    if (!target) return { status: 'FAIL', reason: 'NO_SELECTION' };

    set({ holdSubmitting: true });
    try {
      const sessionId = getOrCreateSessionId();
      const idempotencyKey = crypto.randomUUID();
      const res = await fetch('/api/holds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify({
          sessionId, gameId: state.gameId, mode: 'RECOMMEND',
          seatBundleId: target.seatBundleId, seatIds: target.seatIds,
        }),
      });
      const data: HoldResult = await res.json();
      if (data.status === 'SUCCESS') {
        set({ holdResult: data, holdSubmitting: false });
      } else {
        set({ holdResult: data, holdSubmitting: false, modalOpen: true });
      }
      return data;
    } catch (err) {
      console.error('[useSeatStore] Hold failed:', err);
      const failResult: HoldResult = { status: 'FAIL', reason: 'NETWORK_ERROR' };
      set({ holdResult: failResult, holdSubmitting: false, modalOpen: true });
      return failResult;
    }
  },

  // ─── Map Actions ───

  selectZone: (zoneId) => set({ selectedZoneId: zoneId, selectedSeats: [], seatGrid: [] }),

  setSeatGrid: (grid, rows, cols) => set({ seatGrid: grid, gridRows: rows, gridCols: cols }),

  toggleSeat: (seat) => {
    if (seat.status !== 'AVAILABLE') return;

    const state = get();
    const existing = state.selectedSeats.find(s => s.seatId === seat.seatId);

    if (existing) {
      // Deselect
      set({ selectedSeats: state.selectedSeats.filter(s => s.seatId !== seat.seatId) });
    } else {
      // Select (enforce partySize limit)
      if (state.selectedSeats.length >= state.partySize) return;
      set({ selectedSeats: [...state.selectedSeats, { seatId: seat.seatId, label: seat.label }] });
    }
  },

  submitMapHold: async () => {
    const state = get();
    if (state.selectedSeats.length !== state.partySize) {
      return { status: 'FAIL', reason: 'INCORRECT_SEAT_COUNT' };
    }

    set({ holdSubmitting: true });
    try {
      const sessionId = getOrCreateSessionId();
      const idempotencyKey = crypto.randomUUID();
      const seatIds = state.selectedSeats.map(s => s.seatId);

      const res = await fetch('/api/holds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify({ sessionId, gameId: state.gameId, mode: 'MAP', seatIds }),
      });
      const data: HoldResult = await res.json();
      if (data.status === 'SUCCESS') {
        set({ holdResult: data, holdSubmitting: false });
      } else {
        set({ holdResult: data, holdSubmitting: false, modalOpen: true, selectedSeats: [] });
      }
      return data;
    } catch (err) {
      console.error('[useSeatStore] Map hold failed:', err);
      const failResult: HoldResult = { status: 'FAIL', reason: 'NETWORK_ERROR' };
      set({ holdResult: failResult, holdSubmitting: false, modalOpen: true });
      return failResult;
    }
  },
}));
