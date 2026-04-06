import { Server } from 'lucide-react';

interface ServiceBadgeProps {
  serviceId: string;
  tier?: 1 | 2;
}

export function ServiceBadge({ serviceId, tier }: ServiceBadgeProps) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <Server size={12} className="text-text-muted" />
      <span className="font-mono text-text-secondary">{serviceId}</span>
      {tier != null && (
        <span className={`font-medium ${tier === 1 ? 'text-tier-1' : 'text-tier-2'}`}>
          T{tier}
        </span>
      )}
    </span>
  );
}
