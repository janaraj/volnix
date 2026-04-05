import { ShieldCheck, Shield } from 'lucide-react';

interface FidelityIndicatorProps {
  tier: 1 | 2;
  source?: string;
}

export function FidelityIndicator({ tier, source }: FidelityIndicatorProps) {
  const Icon = tier === 1 ? ShieldCheck : Shield;
  return (
    <span className="inline-flex items-center gap-1 text-xs">
      <Icon size={14} className={tier === 1 ? 'text-tier-1' : 'text-tier-2'} />
      <span className={tier === 1 ? 'text-tier-1' : 'text-tier-2'}>
        Tier {tier}
      </span>
      {source && <span className="text-text-muted">({source})</span>}
    </span>
  );
}
