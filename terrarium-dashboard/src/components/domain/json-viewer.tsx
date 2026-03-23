import { Copy, Check } from 'lucide-react';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';

interface JsonViewerProps {
  data: unknown;
}

/** Escape HTML entities to prevent XSS when injecting into innerHTML. */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Apply syntax highlighting to pre-escaped JSON string. */
function highlightJson(json: string): string {
  const escaped = escapeHtml(json);
  return escaped
    .replace(/(&quot;(?:\\.|[^&])*?&quot;)\s*:/g, '<span class="text-info">$1</span>:')
    .replace(/:\s*(&quot;(?:\\.|[^&])*?&quot;)/g, ': <span class="text-success">$1</span>')
    .replace(/:\s*(\d+\.?\d*)/g, ': <span class="text-warning">$1</span>')
    .replace(/:\s*(true|false|null)/g, ': <span class="text-accent">$1</span>');
}

export function JsonViewer({ data }: JsonViewerProps) {
  const raw = JSON.stringify(data, null, 2);
  const { copy, copied } = useCopyToClipboard();

  return (
    <div className="relative max-h-64 overflow-auto rounded bg-bg-elevated">
      <button
        type="button"
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
