import type { Run } from '@/types/domain';

interface InspectorProps {
  runId: string;
  selectedActorId: string | null;
  run: Run;
}

export function Inspector({ selectedActorId }: InspectorProps) {
  return (
    <div className="text-xs text-text-muted">
      {selectedActorId ? `Inspector: ${selectedActorId} — implementing in F5b` : 'Inspector — implementing in F5b'}
    </div>
  );
}
