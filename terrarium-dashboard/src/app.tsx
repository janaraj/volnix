import { BrowserRouter, Routes, Route } from 'react-router';
import { AppShell } from '@/components/layout/app-shell';
import { RunListPage } from '@/pages/run-list';
import { LiveConsolePage } from '@/pages/live-console';
import { RunReportPage } from '@/pages/run-report';
import { ComparePage } from '@/pages/compare';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<RunListPage />} />
          <Route path="/runs/:id/live" element={<LiveConsolePage />} />
          <Route path="/runs/:id" element={<RunReportPage />} />
          <Route path="/compare" element={<ComparePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
