import { Link, useLocation } from 'react-router';
import { Play, Globe, GitCompareArrows, Hexagon } from 'lucide-react';
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
  { path: '/worlds', label: 'Worlds', icon: Globe },
  { path: '/compare', label: 'Compare', icon: GitCompareArrows },
];

export function Sidebar() {
  const location = useLocation();
  const collapsed = useLayoutStore((s) => s.sidebarCollapsed);

  return (
    <aside className={cn(
      'flex flex-col border-r border-border/50 bg-gradient-to-b from-bg-surface to-bg-base transition-all duration-300',
      collapsed ? 'w-14' : 'w-56',
    )}>
      <div className={cn('flex items-center gap-2.5 p-4 pb-6', collapsed && 'justify-center')}>
        <div className="rounded-lg bg-accent/10 p-1.5">
          <Hexagon size={20} className="text-accent" />
        </div>
        {!collapsed && <span className="text-lg font-semibold tracking-tight">Volnix</span>}
      </div>
      <nav className="flex-1 space-y-1 px-2">
        {NAV_ITEMS.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              title={collapsed ? item.label : undefined}
              aria-current={isActive ? 'page' : undefined}
              className={cn(
                'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors duration-200',
                isActive
                  ? 'bg-accent/10 shadow-sm border border-accent/20 text-text-primary'
                  : 'border border-transparent text-text-secondary hover:bg-bg-hover hover:text-text-primary',
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
