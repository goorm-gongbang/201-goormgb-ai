'use client';

import { useEffect, useState } from 'react';
import { useSeatStore } from '@/stores/useSeatStore';
import { api } from '@/services/apiClient';
import { useSecurityStore } from '@/stores/useSecurityStore';

interface Zone {
  zoneId: string;
  label: string;
  groupId: string;
  remaining: number;
  disabled: boolean;
}

interface ZoneGroup {
  groupId: string;
  label: string;
}

interface ZoneData {
  zones: Zone[];
  groups: ZoneGroup[];
}

export default function ZoneList({ gameId }: { gameId: string }) {
  const [zoneData, setZoneData] = useState<ZoneData | null>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const { selectedZoneId, selectZone } = useSeatStore();
  const lastResult = useSecurityStore((s) => s.lastResult);

  useEffect(() => {
    async function fetchZones() {
      try {
        const data = await api.get<ZoneData>(`/zones?gameId=${gameId}`);
        setZoneData(data);
        if (data.groups.length > 0) setExpandedGroup(data.groups[0].groupId);
      } catch (err) {
        console.error('[ZoneList] Fetch failed:', err);
      }
    }
    fetchZones();
  }, [gameId, lastResult]);

  if (!zoneData) {
    return <div className="flex justify-center py-8"><div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" /></div>;
  }

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-bold text-zinc-700 dark:text-zinc-300 mb-2">구역 선택</h4>
      {zoneData.groups.map((group) => {
        const zones = zoneData.zones.filter(z => z.groupId === group.groupId);
        const isExpanded = expandedGroup === group.groupId;

        return (
          <div key={group.groupId} className="rounded-xl border border-zinc-200 dark:border-zinc-700 overflow-hidden">
            {/* Group Header */}
            <button
              onClick={() => setExpandedGroup(isExpanded ? null : group.groupId)}
              className="w-full flex items-center justify-between px-4 py-2.5 bg-zinc-50 dark:bg-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-750 transition-colors"
            >
              <span className="font-semibold text-sm text-zinc-800 dark:text-zinc-200">
                🏟️ {group.label}
              </span>
              <span className="text-xs text-zinc-400">
                {isExpanded ? '▲' : '▼'}
              </span>
            </button>

            {/* Zone Items */}
            {isExpanded && (
              <div className="divide-y divide-zinc-100 dark:divide-zinc-700">
                {zones.map((zone) => {
                  const isSelected = selectedZoneId === zone.zoneId;
                  return (
                    <button
                      key={zone.zoneId}
                      onClick={() => !zone.disabled && selectZone(zone.zoneId)}
                      disabled={zone.disabled}
                      className={`w-full flex items-center justify-between px-4 py-2.5 text-left transition-all ${
                        zone.disabled
                          ? 'opacity-40 cursor-not-allowed bg-zinc-50 dark:bg-zinc-900'
                          : isSelected
                          ? 'bg-emerald-50 dark:bg-emerald-900/20 border-l-3 border-emerald-500'
                          : 'hover:bg-zinc-50 dark:hover:bg-zinc-800'
                      }`}
                    >
                      <span className={`text-sm ${isSelected ? 'font-bold text-emerald-700 dark:text-emerald-400' : 'text-zinc-700 dark:text-zinc-300'}`}>
                        {zone.label}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        zone.disabled
                          ? 'bg-red-100 text-red-500 dark:bg-red-900/30'
                          : zone.remaining < 10
                          ? 'bg-amber-100 text-amber-600 dark:bg-amber-900/30'
                          : 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30'
                      }`}>
                        {zone.disabled ? '매진' : `${zone.remaining}석`}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
