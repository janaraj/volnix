import { Copy, Check } from 'lucide-react';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';

interface JsonViewerProps {
  data: unknown;
}

function highlightJson(json: string): string {
  return json
    .replace(/("(?:\\.|[^"\\])*")\s*:/g, '<span class="text-info">$1</span>:')
    .replace(/:\s*("(?:\\.|[^"\\])*")/g, ': <span class="text-success">$1</span>')
    .replace(/:\s*(\d+\.?\d*)/g, ': <span class="text-warning">$1</span>')
    .replace(/:\s*(true|false|null)/g, ': <span class="text-accent">$1</span>');
}

export function JsonViewer({ data }: JsonViewerProps) {
  const raw = JSON.stringify(data, null, 2);
  const { copy, copied } = useCopyToClipboard();

  return (
    <div className="relative max-h-64 overflow-auto rounded bg-bg-elevated">
      <button
        onClick={() => copy(raw)}
        className="absolute right-2 top-2 text-text-muted hover:text-text-secondary transition-colors"
        title="Copy JSON"
      >
        {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
      </button>
      <pre
        className="p-3 font-mono text-xs leading-relaxed"
        dangerouslySetInnerHTML={{ __html: highlightJson(raw) }}
      />
    </div>
  );
}
