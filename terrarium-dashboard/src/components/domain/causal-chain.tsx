import { GitBranch, Copy, Check } from 'lucide-react';
import { truncateId } from '@/lib/formatters';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';

interface CausalChainProps {
  eventIds: string[];
  label: string;
}

function CausalEventId({ id }: { id: string }) {
  const { copy, copied } = useCopyToClipboard();
  return (
    <button
      onClick={() => copy(id)}
      title={id}
      className="inline-flex items-center gap-1 font-mono text-xs text-info hover:underline underline-offset-2 transition-colors"
    >
      {truncateId(id, 12)}
      {copied ? <Check size={10} className="text-success" /> : <Copy size={10} className="text-text-muted" />}
    </button>
  );
}

export function CausalChain({ eventIds, label }: CausalChainProps) {
  if (eventIds.length === 0) return null;
  return (
    <div className="text-xs">
      <div className="flex items-center gap-1 text-text-muted mb-1">
        <GitBranch size={12} />
        <span>{label}:</span>
      </div>
      <div className="ml-3 border-l border-border pl-3 space-y-1">
        {eventIds.map((id) => (
          <div key={id} className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-info" />
            <CausalEventId id={id} />
          </div>
        ))}
      </div>
    </div>
  );
}
