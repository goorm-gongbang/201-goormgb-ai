'use client';

import { create } from 'zustand';

interface PaymentState {
  orderId: string | null;
  paymentMethod: string;
  agreeTerms: boolean;
  agreeCancelFee: boolean;
  phoneEditMode: boolean;
  phone: string;
  submitting: boolean;
  expired: boolean;
  result: { status: string; reasonCode?: string } | null;

  // Actions
  setOrderId: (id: string) => void;
  setPaymentMethod: (method: string) => void;
  setAgreeTerms: (v: boolean) => void;
  setAgreeCancelFee: (v: boolean) => void;
  setPhoneEditMode: (v: boolean) => void;
  setPhone: (v: string) => void;
  setExpired: (v: boolean) => void;
  submitPayment: () => Promise<void>;
  reset: () => void;
}

export const usePaymentStore = create<PaymentState>((set, get) => ({
  orderId: null,
  paymentMethod: 'TOSS',
  agreeTerms: false,
  agreeCancelFee: false,
  phoneEditMode: false,
  phone: '',
  submitting: false,
  expired: false,
  result: null,

  setOrderId: (id) => set({ orderId: id }),
  setPaymentMethod: (method) => set({ paymentMethod: method }),
  setAgreeTerms: (v) => set({ agreeTerms: v }),
  setAgreeCancelFee: (v) => set({ agreeCancelFee: v }),
  setPhoneEditMode: (v) => set({ phoneEditMode: v }),
  setPhone: (v) => set({ phone: v }),
  setExpired: (v) => set({ expired: v }),

  submitPayment: async () => {
    const state = get();
    if (!state.orderId || state.expired) return;

    set({ submitting: true });
    try {
      const res = await fetch('/api/payments', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': crypto.randomUUID(),
        },
        body: JSON.stringify({
          orderId: state.orderId,
          method: state.paymentMethod,
        }),
      });
      const data = await res.json();
      set({ result: data, submitting: false });
    } catch {
      set({ result: { status: 'FAILED', reasonCode: 'NETWORK_ERROR' }, submitting: false });
    }
  },

  reset: () => set({
    orderId: null, paymentMethod: 'TOSS', agreeTerms: false, agreeCancelFee: false,
    phoneEditMode: false, phone: '', submitting: false, expired: false, result: null,
  }),
}));

// Derived: canSubmit
export function useCanSubmit() {
  const { agreeTerms, agreeCancelFee, submitting, expired } = usePaymentStore();
  return agreeTerms && agreeCancelFee && !submitting && !expired;
}
