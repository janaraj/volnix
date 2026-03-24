import type { Run } from '@/types/domain';

interface ContextViewProps {
  runId: string;
  run: Run;
  selectedEventId: string | null;
  selectedActorId: string | null;
  eventCount: number;
  onSelectEvent: (eventId: string) => void;
  onClearSelection: () => void;
}

export function ContextView({ selectedEventId, selectedActorId }: ContextViewProps) {
  if (selectedEventId) return <div className="text-sm text-text-muted">Event detail — implementing in F5b</div>;
  if (selectedActorId) return <div className="text-sm text-text-muted">Agent detail — implementing in F5b</div>;
  return <div className="text-sm text-text-muted">Run overview — implementing in F5b</div>;
}
