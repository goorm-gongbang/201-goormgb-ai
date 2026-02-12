'use client';

import { useEffect, useState } from 'react';

interface QueueOverlayProps {
  position: number;
  progress: number;
  status: string;
  estimatedWaitMs: number;
}

const DESCRIPTIONS = [
  '선호하신 조건에 맞는 좌석을 찾고 있어요! 🎯',
  '최적의 관람 경험을 위해 준비 중입니다! 🏟️',
  '잠시만 기다려 주세요, 곧 차례가 됩니다! ⏳',
];

export default function QueueOverlay({
  position,
  progress,
  status,
  estimatedWaitMs,
}: QueueOverlayProps) {
  const [descIndex, setDescIndex] = useState(0);

  // Cycle descriptions every 3 seconds
  useEffect(() => {
    const timer = setInterval(() => {
      setDescIndex((prev) => (prev + 1) % DESCRIPTIONS.length);
    }, 3000);
    return () => clearInterval(timer);
  }, []);

  const progressPercent = Math.min(100, Math.max(0, progress * 100));
  const isGranted = status === 'GRANTED';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      {/* Card */}
      <div className="relative w-full max-w-md mx-4 rounded-3xl bg-white dark:bg-zinc-900 shadow-2xl overflow-hidden">
        {/* Top gradient accent */}
        <div className="h-2 bg-gradient-to-r from-emerald-400 via-teal-500 to-cyan-500" />

        <div className="p-8 space-y-6">
          {/* Avatar placeholder */}
          <div className="flex justify-end">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center text-white text-sm font-bold shadow-lg">
              U
            </div>
          </div>

          {/* Title */}
          <div className="text-center space-y-2">
            <h2 className="text-lg font-bold text-zinc-800 dark:text-white">
              {isGranted ? '🎉 입장 준비 완료!' : '🎫 대기열 안내'}
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 transition-all duration-500">
              {isGranted ? '좌석 선택 페이지로 이동합니다...' : DESCRIPTIONS[descIndex]}
            </p>
          </div>

          {/* Position Display */}
          <div className="text-center py-4">
            <p className="text-xs text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-1">
              현재 대기 순서
            </p>
            <p className="text-5xl font-black tabular-nums">
              <span className="bg-gradient-to-r from-emerald-500 to-teal-600 bg-clip-text text-transparent">
                {isGranted ? '0' : position.toLocaleString()}
              </span>
              <span className="text-base font-medium text-zinc-400 ml-1">번째</span>
            </p>
          </div>

          {/* Progress Bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-zinc-500">
              <span>진행률</span>
              <span>{progressPercent.toFixed(1)}%</span>
            </div>
            <div className="h-3 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-all duration-700 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Estimated Wait */}
          {!isGranted && (
            <div className="flex items-center justify-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              예상 대기시간: {Math.ceil(estimatedWaitMs / 1000)}초
            </div>
          )}

          {/* Loading animation at bottom */}
          {!isGranted && (
            <div className="flex justify-center gap-1 pt-2">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-2 h-2 rounded-full bg-emerald-500 animate-bounce"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
