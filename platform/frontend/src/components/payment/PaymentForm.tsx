'use client';

import { usePaymentStore } from '@/stores/usePaymentStore';

const PAYMENT_METHODS = [
  { id: 'TOSS', label: '토스페이', icon: '💳', color: 'bg-blue-500' },
  { id: 'KAKAO', label: '카카오페이', icon: '🟡', color: 'bg-yellow-400' },
  { id: 'NAVER', label: '네이버페이', icon: '🟢', color: 'bg-green-500' },
  { id: 'CARD', label: '카드 결제', icon: '💳', color: 'bg-zinc-500' },
];

interface PaymentFormProps {
  orderId: string;
  maskedPhone: string | null;
  onPhoneSaved: (masked: string) => void;
}

export default function PaymentForm({ orderId, maskedPhone, onPhoneSaved }: PaymentFormProps) {
  const {
    paymentMethod, setPaymentMethod,
    agreeTerms, setAgreeTerms,
    agreeCancelFee, setAgreeCancelFee,
    phoneEditMode, setPhoneEditMode,
    phone, setPhone,
  } = usePaymentStore();

  const handlePhoneSave = async () => {
    if (!/^\d{10,11}$/.test(phone)) {
      alert('올바른 휴대폰 번호를 입력하세요 (10~11자리 숫자)');
      return;
    }
    try {
      const res = await fetch(`/api/orders/${orderId}/tax`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      });
      const data = await res.json();
      onPhoneSaved(data.maskedPhone);
      setPhoneEditMode(false);
      setPhone('');
    } catch {
      alert('저장 실패');
    }
  };

  return (
    <div className="space-y-6">
      {/* Payment Methods */}
      <section>
        <h3 className="text-base font-bold text-zinc-900 dark:text-white mb-3">결제수단 선택</h3>
        <div className="grid grid-cols-2 gap-3">
          {PAYMENT_METHODS.map((m) => {
            const isSelected = paymentMethod === m.id;
            return (
              <button
                key={m.id}
                onClick={() => setPaymentMethod(m.id)}
                className={`flex items-center gap-3 p-4 rounded-xl border-2 transition-all ${
                  isSelected
                    ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20 shadow-md'
                    : 'border-zinc-200 dark:border-zinc-700 hover:border-zinc-300'
                }`}
              >
                <span className="text-2xl">{m.icon}</span>
                <span className={`text-sm font-medium ${isSelected ? 'text-emerald-700 dark:text-emerald-400' : 'text-zinc-700 dark:text-zinc-300'}`}>
                  {m.label}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {/* Tax Deduction */}
      <section className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-bold text-zinc-700 dark:text-zinc-300">소득공제 정보</h4>
          <button
            onClick={() => setPhoneEditMode(!phoneEditMode)}
            className="text-xs text-emerald-500 hover:underline"
          >
            {phoneEditMode ? '취소' : '변경'}
          </button>
        </div>

        {phoneEditMode ? (
          <div className="flex gap-2">
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="01012345678"
              className="flex-1 px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm"
            />
            <button
              onClick={handlePhoneSave}
              className="px-4 py-2 rounded-lg bg-emerald-500 text-white text-sm font-medium hover:bg-emerald-600 transition-colors"
            >
              저장
            </button>
          </div>
        ) : (
          <p className="text-sm text-zinc-500">
            {maskedPhone || '등록된 번호가 없습니다'}
          </p>
        )}
      </section>

      {/* Agreements */}
      <section className="space-y-3">
        <h3 className="text-base font-bold text-zinc-900 dark:text-white">약관 동의</h3>

        <label className="flex items-start gap-3 cursor-pointer group">
          <input
            type="checkbox"
            checked={agreeTerms}
            onChange={(e) => setAgreeTerms(e.target.checked)}
            className="mt-0.5 h-5 w-5 rounded border-zinc-300 text-emerald-500 focus:ring-emerald-500"
            data-testid="agree-terms"
          />
          <div>
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">[필수] 이용약관 동의</p>
            <p className="text-xs text-zinc-400">예매 이용약관에 동의합니다.</p>
          </div>
        </label>

        <label className="flex items-start gap-3 cursor-pointer group">
          <input
            type="checkbox"
            checked={agreeCancelFee}
            onChange={(e) => setAgreeCancelFee(e.target.checked)}
            className="mt-0.5 h-5 w-5 rounded border-zinc-300 text-emerald-500 focus:ring-emerald-500"
            data-testid="agree-cancel-fee"
          />
          <div>
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">[필수] 취소 수수료 안내 동의</p>
            <p className="text-xs text-zinc-400">경기일 기준 취소 수수료가 발생할 수 있습니다.</p>
          </div>
        </label>
      </section>
    </div>
  );
}
