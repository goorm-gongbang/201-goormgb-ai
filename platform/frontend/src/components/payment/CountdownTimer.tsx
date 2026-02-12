'use client';

import { useEffect, useState } from 'react';

interface CountdownTimerProps {
  expiresAt: string; // ISO string
  onExpired: () => void;
}

export default function CountdownTimer({ expiresAt, onExpired }: CountdownTimerProps) {
  const [remaining, setRemaining] = useState<number>(0);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    function calc() {
      const diff = new Date(expiresAt).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining(0);
        setExpired(true);
        onExpired();
        return false;
      }
      setRemaining(Math.ceil(diff / 1000));
      return true;
    }

    if (!calc()) return;

    const interval = setInterval(() => {
      if (!calc()) clearInterval(interval);
    }, 1000);

    return () => clearInterval(interval);
  }, [expiresAt, onExpired]);

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  const display = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

  const isUrgent = remaining <= 60;

  return (
    <div className={`flex items-center gap-2 font-mono text-xl font-bold ${
      expired
        ? 'text-red-500'
        : isUrgent
        ? 'text-amber-500 animate-pulse'
        : 'text-zinc-900 dark:text-white'
    }`}>
      <span className="text-sm">⏱️</span>
      <span data-testid="countdown-timer">{display}</span>
      {expired && <span className="text-xs text-red-400 font-normal ml-1">만료됨</span>}
    </div>
  );
}
