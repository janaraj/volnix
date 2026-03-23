import { Link } from 'react-router';
import { Copy, Check } from 'lucide-react';
import { runReportPath } from '@/constants/routes';
import { truncateId } from '@/lib/formatters';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';

interface EntityLinkProps {
  runId: string;
  entityId: string;
  children?: React.ReactNode;
}

export function EntityLink({ runId, entityId, children }: EntityLinkProps) {
  const { copy, copied } = useCopyToClipboard();
  return (
    <span className="inline-flex items-center gap-1">
      <Link
        to={`${runReportPath(runId)}?tab=entities&entity=${entityId}`}
        className="font-mono text-xs text-info underline-offset-2 hover:underline"
        title={entityId}
      >
        {children ?? truncateId(entityId, 12)}
      </Link>
      <button
        onClick={(e) => { e.stopPropagation(); copy(entityId); }}
        className="text-text-muted hover:text-text-secondary transition-colors"
        title="Copy ID"
      >
        {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
      </button>
    </span>
  );
}
