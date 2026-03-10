'use client';

import { useSearchParams } from 'next/navigation';
import { useMemo } from 'react';
import { SESSION_STORAGE_KEYS, STORAGE_KEYS } from '@/contracts/http';

function getTerminalMessage(reasonCode: string): string {
  switch (reasonCode) {
    case 'BLOCKED':
      return '비정상 요청이 감지되어 예매가 종료되었습니다.';
    case 'ABORT':
      return '요청이 중단되어 예매가 종료되었습니다.';
    default:
      return '요청을 처리할 수 없어 예매가 종료되었습니다.';
  }
}

export default function TerminalPage() {
  const searchParams = useSearchParams();
  const reasonFromQuery = searchParams.get('reasonCode') ?? '';
  const httpStatusFromQuery = searchParams.get('httpStatus') ?? '';

  const {
    reasonCode,
    httpStatus,
    message,
  } = useMemo(() => {
    const reason =
      reasonFromQuery
      || (typeof window !== 'undefined'
        ? sessionStorage.getItem(SESSION_STORAGE_KEYS.TERMINAL_REASON) ?? ''
        : '');

    const status =
      httpStatusFromQuery
      || (typeof window !== 'undefined'
        ? sessionStorage.getItem(SESSION_STORAGE_KEYS.TERMINAL_HTTP_STATUS) ?? ''
        : '');

    const msg =
      (typeof window !== 'undefined'
        ? sessionStorage.getItem(SESSION_STORAGE_KEYS.TERMINAL_MESSAGE) ?? ''
        : '')
      || getTerminalMessage(reason || 'UNKNOWN');

    return {
      reasonCode: reason || 'UNKNOWN',
      httpStatus: status || '-',
      message: msg,
    };
  }, [httpStatusFromQuery, reasonFromQuery]);

  const handleRestart = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(STORAGE_KEYS.TM_SESSION_ID);
      localStorage.removeItem(STORAGE_KEYS.TM_VQA_PASSED_SESSION_ID);

      sessionStorage.removeItem(SESSION_STORAGE_KEYS.TERMINAL_REASON);
      sessionStorage.removeItem(SESSION_STORAGE_KEYS.TERMINAL_HTTP_STATUS);
      sessionStorage.removeItem(SESSION_STORAGE_KEYS.TERMINAL_MESSAGE);

      window.location.assign('/games/game-001');
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-lg rounded-2xl border border-red-800/60 bg-zinc-900 shadow-2xl p-8 space-y-6">
        <div className="text-center space-y-2">
          <p className="text-4xl">⛔</p>
          <h1 className="text-2xl font-bold text-white">예매가 종료되었습니다</h1>
          <p className="text-sm text-zinc-300">{message}</p>
        </div>

        <div className="rounded-xl border border-zinc-700 bg-zinc-950 p-4 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-zinc-400">reasonCode</span>
            <span className="font-mono text-red-300">{reasonCode}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-400">httpStatus</span>
            <span className="font-mono text-zinc-200">{httpStatus}</span>
          </div>
        </div>

        <button
          onClick={handleRestart}
          className="w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 transition-all"
        >
          새 세션으로 다시 시작
        </button>
      </div>
    </div>
  );
}
