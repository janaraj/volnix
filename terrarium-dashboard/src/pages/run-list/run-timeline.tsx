import { cn } from '@/lib/cn';
import type { RunStatus } from '@/types/domain';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RunTimelineProps {
  status: RunStatus;
  eventCount?: number;
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

const STEPS = ['Created', 'Compiling', 'Running', 'Completed'] as const;

function resolveCurrentStep(status: RunStatus, eventCount: number): number {
  switch (status) {
    case 'created':
      // If created, compilation is happening in the background
      return 1;
    case 'running':
      return eventCount === 0 ? 1 : 2;
    case 'completed':
      return 3;
    case 'failed':
    case 'stopped':
      return eventCount === 0 ? 1 : 2;
    default:
      return 0;
  }
}

function isFailed(status: RunStatus): boolean {
  return status === 'failed' || status === 'stopped';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RunTimeline({ status, eventCount = 0 }: RunTimelineProps) {
  const currentStep = resolveCurrentStep(status, eventCount);
  const failed = isFailed(status);

  return (
    <div className="flex items-center gap-0" aria-label="Run progress">
      {STEPS.map((label, i) => {
        const isCompleted = i < currentStep;
        const isCurrent = i === currentStep;
        const isUpcoming = i > currentStep;
        const isFailedStep = isCurrent && failed;

        return (
          <div key={label} className="flex items-center">
            {/* Arrow separator (skip before first step) */}
            {i > 0 && (
              <span
                className={cn(
                  'mx-1 text-[10px] leading-none',
                  isCompleted || isCurrent ? 'text-text-muted' : 'text-text-muted/40',
                )}
                aria-hidden
              >
                &rarr;
              </span>
            )}

            {/* Dot — pulses when current step is active */}
            <span
              className={cn(
                'inline-block h-2 w-2 rounded-full mr-1 shrink-0',
                isFailedStep && 'bg-error',
                !isFailedStep && isCompleted && 'bg-success',
                !isFailedStep && isCurrent && 'bg-warning animate-pulse',
                !isFailedStep && isUpcoming && 'bg-zinc-400/40',
              )}
              aria-hidden
            />

            {/* Label */}
            <span
              className={cn(
                'text-[11px] leading-none whitespace-nowrap',
                isFailedStep && 'text-error font-medium',
                !isFailedStep && isCompleted && 'text-success',
                !isFailedStep && isCurrent && 'text-warning font-medium',
                !isFailedStep && isUpcoming && 'text-text-muted/50',
              )}
            >
              {isFailedStep ? (status === 'failed' ? 'Failed' : 'Stopped') : label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
