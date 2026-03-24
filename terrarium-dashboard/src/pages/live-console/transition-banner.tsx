import { Link } from 'react-router';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { runReportPath } from '@/constants/routes';

interface TransitionBannerProps {
  runId: string;
  visible: boolean;
}

export function TransitionBanner({ runId, visible }: TransitionBannerProps) {
  if (!visible) return null;

  return (
    <div className="flex items-center gap-3 border-b border-success/30 bg-success/10 px-4 py-2 text-sm text-success">
      <CheckCircle2 size={18} />
      <span className="font-medium">Run completed</span>
      <Link
        to={runReportPath(runId)}
        className="ml-auto flex items-center gap-1 transition-colors hover:text-success/80"
      >
        View report
        <ArrowRight size={14} />
      </Link>
    </div>
  );
}
