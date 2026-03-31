'use client';

import { useState, useRef, useEffect } from 'react';
import { useSecurityStore } from '@/stores/useSecurityStore';
import { getOrCreateSessionId } from '@/services/api';
import CatchBallVqaDemo from '@/components/security/CatchBallVqaDemo';

export default function SecurityLayer() {
  const {
    isVisible,
    challengeData,
    status,
    errorMessage,
    remainingAttempts,
    submitAnswer,
    hideChallenge,
  } = useSecurityStore();

  const [answer, setAnswer] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when challenge shows
  useEffect(() => {
    if (isVisible && status === 'IDLE' && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isVisible, status]);

  if (!isVisible) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!answer.trim() || status === 'SUBMITTING') return;
    const ok = await submitAnswer(answer.trim());
    if (!ok) {
      setAnswer('');
      inputRef.current?.focus();
    }
  };

  const isLoading = status === 'LOADING';
  const isSubmitting = status === 'SUBMITTING';
  const isCatchBall = challengeData?.type === 'CATCH_BALL' || challengeData?.type === 'catch_ball';
  const sessionId = getOrCreateSessionId();

  const handleCatchBallSuccess = async (telemetry: Record<string, unknown>) => {
    if (isSubmitting) return;
    const ok = await submitAnswer('__VQA_PASS__', telemetry);
    if (!ok) {
      // keep modal open and show backend verification failure message.
      return;
    }
    hideChallenge();
  };

  const handleCatchBallBlocked = async (telemetry: Record<string, unknown>) => {
    if (isSubmitting) return;
    await submitAnswer('__VQA_FAIL__', telemetry);
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-md"
      data-testid="security-overlay"
    >
      {/* Modal Card */}
      <div
        className={`relative w-full mx-4 rounded-3xl bg-white dark:bg-zinc-900 shadow-2xl overflow-hidden ${
          isCatchBall ? 'max-w-[1100px]' : 'max-w-sm'
        }`}
      >
        {/* Top accent bar */}
        <div className="h-2 bg-gradient-to-r from-rose-500 via-orange-500 to-amber-500" />

        <div className={`${isCatchBall ? 'p-4 space-y-3' : 'p-8 space-y-6'}`}>
          {/* Shield Icon */}
          <div className="flex justify-center">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-rose-100 to-orange-100 dark:from-rose-900/30 dark:to-orange-900/30 flex items-center justify-center">
              <span className="text-3xl">🛡️</span>
            </div>
          </div>

          {/* Title */}
          <div className="text-center space-y-1">
            <h2 className="text-xl font-bold text-zinc-900 dark:text-white">
              보안 확인
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              부정 예매 방지를 위한 본인 확인입니다.
            </p>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="flex justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-3 border-rose-500 border-t-transparent" />
            </div>
          )}

          {/* Catch-ball VQA */}
          {!isLoading && challengeData && isCatchBall && (
            <div className="space-y-3">
              <p className="text-xs text-center text-zinc-500 dark:text-zinc-400">
                공 도착 위치 + 타이밍을 동시에 맞추면 통과됩니다.
              </p>
              <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-950 p-2">
                <CatchBallVqaDemo
                  embedded
                  challengeId={challengeData.challengeId}
                  sessionId={sessionId}
                  issuedAt={challengeData.issuedAt}
                  onSuccess={handleCatchBallSuccess}
                  onBlocked={handleCatchBallBlocked}
                />
              </div>
              {errorMessage && (
                <p className="text-center text-sm text-rose-500 font-medium animate-pulse" data-testid="security-error">
                  {errorMessage}
                </p>
              )}
            </div>
          )}

          {/* Legacy Quiz Form */}
          {!isLoading && challengeData && !isCatchBall && (
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Quiz Prompt */}
              <div className="rounded-2xl bg-zinc-100 dark:bg-zinc-800 p-4 text-center">
                <p className="text-sm text-zinc-500 mb-1">문제</p>
                <p className="text-2xl font-bold text-zinc-900 dark:text-white">
                  {challengeData.prompt}
                </p>
              </div>

              {/* Answer Input */}
              <input
                ref={inputRef}
                type="text"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="정답을 입력하세요"
                className="w-full px-4 py-3 rounded-xl border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-white text-center text-lg font-medium focus:outline-none focus:ring-2 focus:ring-rose-500 transition-all"
                data-testid="security-input"
                disabled={isSubmitting}
                autoComplete="off"
              />

              {/* Error Message */}
              {errorMessage && (
                <div className="text-center">
                  <p className="text-sm text-rose-500 font-medium animate-pulse" data-testid="security-error">
                    {errorMessage}
                  </p>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting || !answer.trim()}
                className="w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-rose-500 to-orange-500 hover:from-rose-600 hover:to-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-lg hover:shadow-xl"
                data-testid="security-submit"
              >
                {isSubmitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    확인 중...
                  </span>
                ) : (
                  '확인'
                )}
              </button>

              {/* Remaining attempts */}
              <p className="text-center text-xs text-zinc-400">
                남은 기회: {remainingAttempts}회
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
