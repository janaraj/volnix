import { useParams } from 'react-router';
import { useRun } from '@/hooks/queries/use-runs';
import { useUrlTabs } from '@/hooks/use-url-tabs';
import { QueryGuard } from '@/components/feedback/query-guard';
import { EmptyState } from '@/components/feedback/empty-state';
import { cn } from '@/lib/cn';
import type { ReportTabId } from '@/types/ui';
import type { Run } from '@/types/domain';
import { ReportHeader } from './report-header';
import { OverviewTab } from './tabs/overview-tab';
import { ScorecardTab } from './tabs/scorecard-tab';
import { EventsTab } from './tabs/events-tab';
import { EntitiesTab } from './tabs/entities-tab';
import { GapsTab } from './tabs/gaps-tab';
import { ConditionsTab } from './tabs/conditions-tab';

const TAB_ORDER: ReportTabId[] = [
  'overview',
  'scorecard',
  'events',
  'entities',
  'gaps',
  'conditions',
];

const TAB_LABELS: Record<ReportTabId, string> = {
  overview: 'Overview',
  scorecard: 'Scorecard',
  events: 'Events',
  entities: 'Entities',
  gaps: 'Gaps',
  conditions: 'Conditions',
};

function ActiveTab({ tab, runId, run }: { tab: ReportTabId; runId: string; run: Run }) {
  switch (tab) {
    case 'overview':
      return <OverviewTab runId={runId} run={run} />;
    case 'scorecard':
      return <ScorecardTab runId={runId} services={run.services ?? []} />;
    case 'events':
      return <EventsTab runId={runId} />;
    case 'entities':
      return <EntitiesTab runId={runId} />;
    case 'gaps':
      return <GapsTab runId={runId} />;
    case 'conditions':
      return run.conditions
        ? <ConditionsTab conditions={run.conditions} realityPreset={run.reality_preset} behavior={run.config_snapshot?.behavior ?? 'static'} />
        : <EmptyState title="No conditions" description="This run has no world conditions data." />;
  }
}

export function RunReportPage() {
  const { id } = useParams<{ id: string }>();
  const runQuery = useRun(id!);
  const [tab, setTab] = useUrlTabs('overview');

  return (
    <QueryGuard query={runQuery}>
      {(run) => (
        <div>
          <ReportHeader run={run} />
          <div className="flex gap-2 border-b border-bg-elevated pb-0 text-sm">
            {TAB_ORDER.map((tabId) => (
              <button
                key={tabId}
                type="button"
                onClick={() => setTab(tabId)}
                className={cn(
                  'px-3 py-2 text-text-secondary transition-colors hover:text-text-primary',
                  tab === tabId && 'border-b-2 border-info text-text-primary',
                )}
              >
                {TAB_LABELS[tabId]}
              </button>
            ))}
          </div>
          <div className="mt-4">
            <ActiveTab tab={tab as ReportTabId} runId={id!} run={run} />
          </div>
        </div>
      )}
    </QueryGuard>
  );
}
