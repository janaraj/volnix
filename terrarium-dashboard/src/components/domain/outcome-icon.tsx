import type { LucideIcon } from 'lucide-react';
import { CheckCircle2, XCircle, PauseCircle, ArrowUpCircle, AlertCircle, Circle, Flag } from 'lucide-react';
import type { Outcome } from '@/types/domain';
import { outcomeToColorClass } from '@/lib/classifiers';

interface OutcomeIconProps {
  outcome: Outcome;
  size?: number;
}

const OUTCOME_ICONS: Record<string, LucideIcon> = {
  success: CheckCircle2,
  denied: XCircle,
  held: PauseCircle,
  escalated: ArrowUpCircle,
  error: AlertCircle,
  gap: Circle,
  flagged: Flag,
};

export function OutcomeIcon({ outcome, size = 16 }: OutcomeIconProps) {
  const Icon = OUTCOME_ICONS[outcome] ?? Circle;
  return <Icon size={size} className={outcomeToColorClass(outcome)} aria-label={outcome} />;
}
