import { useRunEvents } from '@/hooks/queries/use-events';
import { QueryGuard } from '@/components/feedback/query-guard';
import { SectionLoading } from '@/components/feedback/section-loading';
import { ChatView } from '@/pages/live-console/chat-view';

interface ChatTabProps {
  runId: string;
}

export function ChatTab({ runId }: ChatTabProps) {
  // Same params as LiveConsolePage so the TanStack Query cache is shared
  // across /runs/:id and /runs/:id/live (no duplicate fetch).
  const eventsQuery = useRunEvents(runId, { sort: 'desc', limit: 500 });

  return (
    <QueryGuard query={eventsQuery} loadingFallback={<SectionLoading />}>
      {(data) => <ChatView events={data.events} inline />}
    </QueryGuard>
  );
}
