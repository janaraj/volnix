import { Outlet } from 'react-router';
import { Sidebar } from './sidebar';
import { StatusBar } from './status-bar';

export function AppShell() {
  return (
    <div className="flex h-screen bg-bg-base text-text-primary">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
        <StatusBar connectionStatus="disconnected" />
      </div>
    </div>
  );
}
