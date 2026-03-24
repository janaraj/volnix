import type { RefObject } from 'react';
import { captureElementAsPng } from '@/lib/export';
import { Download } from 'lucide-react';

interface ExportButtonProps {
  targetRef: RefObject<HTMLDivElement | null>;
}

export function ExportButton({ targetRef }: ExportButtonProps) {
  const handleClick = () => {
    if (targetRef.current) {
      captureElementAsPng(targetRef.current, 'terrarium-comparison.png');
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className="flex items-center gap-1.5 rounded bg-bg-elevated px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary"
    >
      <Download size={14} />
      Export PNG
    </button>
  );
}
