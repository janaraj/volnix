import { Link, useLocation } from 'react-router';
import { Play, GitCompareArrows, Hexagon } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useLayoutStore } from '@/stores/layout-store';
import type { LucideIcon } from 'lucide-react';

interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Runs', icon: Play },
  { path: '/compare', label: 'Compare', icon: GitCompareArrows },
];

export function Sidebar() {
  const location = useLocation();
  const collapsed = useLayoutStore((s) => s.sidebarCollapsed);

  return (
    <aside className={cn(
      'flex flex-col border-r border-border bg-bg-surface transition-all',
      collapsed ? 'w-14' : 'w-56',
    )}>
      <div className={cn('flex items-center gap-2 p-4', collapsed && 'justify-center')}>
        <Hexagon size={20} className="text-accent" />
        {!collapsed && <span className="text-lg font-semibold tracking-tight">Terrarium</span>}
      </div>
      <nav className="flex-1 space-y-1 px-2">
        {NAV_ITEMS.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              title={collapsed ? item.label : undefined}
              className={cn(
                'flex items-center gap-2 rounded px-3 py-2 text-sm transition-colors',
                isActive
                  ? 'border-l-2 border-accent bg-bg-elevated text-text-primary'
                  : 'border-l-2 border-transparent text-text-secondary hover:bg-bg-hover hover:text-text-primary',
                collapsed && 'justify-center px-2',
              )}
            >
              <item.icon size={16} />
              {!collapsed && item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
