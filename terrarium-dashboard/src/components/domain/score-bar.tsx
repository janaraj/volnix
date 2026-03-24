import { interpolateScoreColor } from '@/lib/color-utils';
import { formatScore } from '@/lib/formatters';

interface ScoreBarProps {
  value: number;
  label?: string;
  formula?: string;
}

export function ScoreBar({ value, label, formula }: ScoreBarProps) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const hoverText = formula ? `${formatScore(value)} — ${formula}` : undefined;
  return (
    <div className="flex items-center gap-2" title={hoverText}>
      {label && <span className="w-32 truncate text-sm text-text-secondary">{label}</span>}
      <div className="h-2 flex-1 rounded-full bg-bg-elevated">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: interpolateScoreColor(value) }}
        />
      </div>
      <span className="w-8 text-right font-mono text-xs text-text-primary">{formatScore(value)}</span>
    </div>
  );
}
