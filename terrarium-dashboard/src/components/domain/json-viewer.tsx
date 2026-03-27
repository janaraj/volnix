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
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Apply syntax highlighting to a pre-escaped JSON string.
 *
 * Safety: input MUST be escaped via escapeHtml() first.
 * The regexes only match patterns produced by JSON.stringify + escapeHtml:
 * - Keys: `&quot;...&quot;:` → info color
 * - String values: `: &quot;...&quot;` → success color
 * - Number values: `: 123` → warning color
 * - Keyword values: `: true|false|null` → accent color
 *
 * The span class names are static strings — never user-derived.
 */
function highlightJson(json: string): string {
  const escaped = escapeHtml(json);
  return escaped
    .replace(/(&quot;(?:\\.|[^&])*?&quot;)\s*:/g, '<span class="text-info">$1</span>:')
    .replace(/:\s*(&quot;(?:\\.|[^&])*?&quot;)/g, ': <span class="text-success">$1</span>')
    .replace(/:\s*(-?\d+\.?\d*)/g, ': <span class="text-warning">$1</span>')
    .replace(/:\s*(true|false|null)\b/g, ': <span class="text-accent">$1</span>');
}

export function JsonViewer({ data }: JsonViewerProps) {
  const raw = JSON.stringify(data ?? null, null, 2) ?? 'null';
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
