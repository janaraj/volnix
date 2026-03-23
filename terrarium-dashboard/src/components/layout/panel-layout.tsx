import type { ReactNode } from 'react';

interface PanelLayoutProps {
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
}

export function PanelLayout({ left, center, right }: PanelLayoutProps) {
  return (
    <div className="flex h-full">
      <div className="min-w-0 w-1/4 overflow-auto bg-bg-surface p-4">{left}</div>
      <div className="w-px bg-border" />
      <div className="min-w-0 flex-1 overflow-auto bg-bg-surface p-4">{center}</div>
      <div className="w-px bg-border" />
      <div className="min-w-0 w-1/4 overflow-auto bg-bg-surface p-4">{right}</div>
    </div>
  );
}
