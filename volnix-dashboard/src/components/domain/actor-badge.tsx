import { User, Check } from 'lucide-react';
import { truncateId } from '@/lib/formatters';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';

interface ActorBadgeProps {
  actorId: string;
  role?: string;
}

export function ActorBadge({ actorId, role }: ActorBadgeProps) {
  const { copy, copied } = useCopyToClipboard();
  return (
    <button
      type="button"
      onClick={() => copy(actorId)}
      title={actorId}
      className="inline-flex items-center gap-1 font-mono text-xs hover:text-text-primary transition-colors"
    >
      {copied ? <Check size={12} className="text-success" /> : <User size={12} className="text-text-muted" />}
      <span className="text-text-secondary">{truncateId(actorId, 16)}</span>
      {role && <span className="text-text-muted">({role})</span>}
    </button>
  );
}
