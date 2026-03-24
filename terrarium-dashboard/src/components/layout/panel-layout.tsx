import type { ReactNode } from 'react';

interface PanelLayoutProps {
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
}

export function PanelLayout({ left, center, right }: PanelLayoutProps) {
  return (
    <div className="flex h-full flex-col md:flex-row">
      <div className="min-w-0 md:w-1/4 overflow-auto bg-bg-surface p-4 border-b md:border-b-0 md:border-r border-border">
        {left}
      </div>
      <div className="min-w-0 flex-1 overflow-auto bg-bg-surface p-4">{center}</div>
      <div className="min-w-0 md:w-1/4 overflow-auto bg-bg-surface p-4 border-t md:border-t-0 md:border-l border-border">
        {right}
      </div>
    </div>
  );
}
