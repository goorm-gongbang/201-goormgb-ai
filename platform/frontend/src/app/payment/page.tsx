'use client';

import { useEffect, useState, useCallback, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { usePaymentStore } from '@/stores/usePaymentStore';
import PaymentForm from '@/components/payment/PaymentForm';
import MyBookingInfoPanel from '@/components/payment/MyBookingInfoPanel';

interface OrderDetail {
  orderId: string;
  gameId: string;
  status: string;
  seatIds: string[];
  totalPrice: number;
  maskedPhone: string | null;
  expiresAt: string;
  createdAt: string;
  gameTitle: string;
  gameDate: string;
  venue: string;
}

function PaymentContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const orderId = searchParams.get('orderId');
  const { setOrderId, setExpired, result, expired } = usePaymentStore();

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [maskedPhone, setMaskedPhone] = useState<string | null>(null);

  // Redirect if no orderId
  useEffect(() => {
    if (!orderId) {
      router.replace('/seats');
      return;
    }
    setOrderId(orderId);
  }, [orderId, router, setOrderId]);

  // Fetch order detail
  useEffect(() => {
    if (!orderId) return;

    async function fetchOrder() {
      try {
        const res = await fetch(`/api/orders/${orderId}`);
        if (!res.ok) {
          router.replace('/seats');
          return;
        }
        const data: OrderDetail = await res.json();
        setOrder(data);
        setMaskedPhone(data.maskedPhone);

        if (data.status === 'EXPIRED') {
          setExpired(true);
        }
      } catch {
        router.replace('/seats');
      } finally {
        setLoading(false);
      }
    }
    fetchOrder();
  }, [orderId, router, setExpired]);

  // Handle payment success → navigate to done page
  useEffect(() => {
    if (result?.status === 'SUCCEEDED') {
      router.push(`/payment/done?orderId=${orderId}`);
    }
  }, [result, orderId, router]);

  const handleExpired = useCallback(() => {
    setExpired(true);
    setTimeout(() => {
      alert('결제 시간이 만료되었습니다.');
      router.push('/seats');
    }, 500);
  }, [setExpired, router]);

  if (!orderId || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="h-8 w-8 animate-spin rounded-full border-3 border-rose-500 border-t-transparent" />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <p className="text-zinc-400">주문 정보를 찾을 수 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold text-zinc-900 dark:text-white">
              🎫 Traffic-Master
            </h1>
            <span className="text-xs text-zinc-500">좌석 선택 &gt; <strong>주문서</strong> &gt; 결제하기</span>
          </div>
          <span className="text-xs px-2 py-1 rounded-full bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400 font-medium">
            Stage 6 · PAYMENT
          </span>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left: Payment Form (3/5) */}
          <div className="lg:col-span-3">
            <div className="rounded-2xl border border-zinc-200 bg-white shadow-lg p-6 dark:bg-zinc-900 dark:border-zinc-700">
              <PaymentForm
                orderId={order.orderId}
                maskedPhone={maskedPhone}
                onPhoneSaved={(mp) => setMaskedPhone(mp)}
              />
            </div>
          </div>

          {/* Right: Booking Info (2/5) */}
          <div className="lg:col-span-2">
            <div className="lg:sticky lg:top-20 rounded-2xl border border-zinc-200 bg-white shadow-lg p-6 dark:bg-zinc-900 dark:border-zinc-700">
              <MyBookingInfoPanel
                order={order}
                onExpired={handleExpired}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function PaymentPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <div className="h-8 w-8 animate-spin rounded-full border-3 border-rose-500 border-t-transparent" />
      </div>
    }>
      <PaymentContent />
    </Suspense>
  );
}
