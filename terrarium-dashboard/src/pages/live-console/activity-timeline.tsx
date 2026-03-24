import { useMemo } from 'react';
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { WorldEvent } from '@/types/domain';
import { interpolateScoreColor } from '@/lib/color-utils';

interface ActivityTimelineProps {
  events: WorldEvent[];
  onJumpToTick: (tick: number) => void;
}

const BUCKET_COUNT = 50;

export function ActivityTimeline({ events, onJumpToTick }: ActivityTimelineProps) {
  const chartData = useMemo(() => {
    if (events.length === 0) return [];
    const maxTick = Math.max(...events.map((e) => e.timestamp.tick));
    const bucketSize = Math.max(1, Math.ceil(maxTick / BUCKET_COUNT));
    const buckets: Array<{ tick: number; count: number; successRate: number }> = [];

    for (let i = 0; i < BUCKET_COUNT; i++) {
      const startTick = i * bucketSize;
      const endTick = (i + 1) * bucketSize;
      const bucketEvents = events.filter(
        (e) => e.timestamp.tick >= startTick && e.timestamp.tick < endTick,
      );
      const successCount = bucketEvents.filter((e) => e.outcome === 'success').length;
      buckets.push({
        tick: startTick,
        count: bucketEvents.length,
        successRate: bucketEvents.length > 0 ? successCount / bucketEvents.length : 1,
      });
    }
    return buckets;
  }, [events]);

  if (chartData.length === 0) return null;

  return (
    <div className="h-12 w-full border-t border-border bg-bg-surface px-4 py-1">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          onClick={(data) => {
            if (data?.activePayload?.[0]) {
              onJumpToTick(data.activePayload[0].payload.tick);
            }
          }}
        >
          <XAxis dataKey="tick" hide />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.[0]) return null;
              const d = payload[0].payload;
              return (
                <div className="rounded bg-bg-elevated px-2 py-1 text-xs">
                  Tick {d.tick}: {d.count} events
                </div>
              );
            }}
          />
          <Bar dataKey="count" cursor="pointer">
            {chartData.map((entry, idx) => (
              <Cell key={idx} fill={interpolateScoreColor(entry.successRate)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
