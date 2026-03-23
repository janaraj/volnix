import type { LucideIcon } from 'lucide-react';
import { ShieldAlert, ShieldX, ArrowUpCircle, FileText } from 'lucide-react';
import { enforcementToColorClass } from '@/lib/classifiers';

interface EnforcementBadgeProps {
  enforcement: 'hold' | 'block' | 'escalate' | 'log';
}

const ENFORCEMENT_ICONS: Record<string, LucideIcon> = {
  hold: ShieldAlert,
  block: ShieldX,
  escalate: ArrowUpCircle,
  log: FileText,
};

export function EnforcementBadge({ enforcement }: EnforcementBadgeProps) {
  const Icon = ENFORCEMENT_ICONS[enforcement] ?? FileText;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium uppercase ${enforcementToColorClass(enforcement)}`}>
      <Icon size={14} />
      {enforcement}
    </span>
  );
}
