'use client';

import { useState } from 'react';
import type { GameDetail } from '@/types';

interface GameInfoTabsProps {
  game: GameDetail;
}

type TabKey = 'info' | 'price';

export default function GameInfoTabs({ game }: GameInfoTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('info');

  const gameDate = new Date(game.dateTime);
  const formattedDate = gameDate.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  });
  const formattedTime = gameDate.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className="space-y-4">
      {/* Tab Headers */}
      <div className="flex border-b border-zinc-200 dark:border-zinc-700">
        <button
          onClick={() => setActiveTab('info')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'info'
              ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
              : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400'
          }`}
        >
          경기 정보
        </button>
        <button
          onClick={() => setActiveTab('price')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'price'
              ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
              : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400'
          }`}
        >
          가격표
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'info' && (
        <div className="space-y-6">
          {/* Match Header */}
          <div className="flex items-center justify-center gap-6 py-6">
            <div className="text-center space-y-2">
              <div className="w-16 h-16 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-2xl">
                🏠
              </div>
              <p className="text-sm font-bold text-zinc-800 dark:text-zinc-200">
                {game.homeTeam.name}
              </p>
            </div>
            <div className="text-center">
              <span className="text-2xl font-black text-zinc-400">VS</span>
            </div>
            <div className="text-center space-y-2">
              <div className="w-16 h-16 rounded-full bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-2xl">
                ✈️
              </div>
              <p className="text-sm font-bold text-zinc-800 dark:text-zinc-200">
                {game.awayTeam.name}
              </p>
            </div>
          </div>

          {/* Game Details Grid */}
          <div className="grid grid-cols-2 gap-4">
            <InfoItem icon="📅" label="날짜" value={formattedDate} />
            <InfoItem icon="🕐" label="시간" value={formattedTime} />
            <InfoItem icon="🏟️" label="경기장" value={game.venue.name} />
            <InfoItem icon="📍" label="위치" value={game.venue.location} />
            <InfoItem
              icon="⏳"
              label="D-Day"
              value={game.dDay > 0 ? `D-${game.dDay}` : game.dDay === 0 ? 'D-Day' : '종료'}
            />
          </div>
        </div>
      )}

      {activeTab === 'price' && (
        <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-zinc-50 dark:bg-zinc-800">
                <th className="px-4 py-3 text-left font-semibold text-zinc-600 dark:text-zinc-300">
                  좌석 등급
                </th>
                <th className="px-4 py-3 text-right font-semibold text-zinc-600 dark:text-zinc-300">
                  가격
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {game.priceTable.map((item) => (
                <tr key={item.grade} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                  <td className="px-4 py-3 text-zinc-800 dark:text-zinc-200 flex items-center gap-2">
                    <span
                      className="inline-block w-3 h-3 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    {item.grade}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-zinc-800 dark:text-zinc-200">
                    ₩{item.price.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function InfoItem({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2 p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800">
      <span className="text-lg">{icon}</span>
      <div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
        <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{value}</p>
      </div>
    </div>
  );
}
