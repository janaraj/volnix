import type { Run } from '@/types/domain';

interface RunRowProps {
  run: Run;
}

export function RunRow({ run }: RunRowProps) {
  return <div className="font-mono text-xs">[RunRow: {run.id}]</div>;
}
