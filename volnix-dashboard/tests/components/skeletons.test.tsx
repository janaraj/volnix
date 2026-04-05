import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  MetricCardsSkeleton,
  EventFeedSkeleton,
  ScorecardGridSkeleton,
  EntityCardSkeleton,
} from '@/components/feedback/skeletons';

describe('Skeleton components', () => {
  it('MetricCardsSkeleton renders 4 cards', () => {
    const { container } = render(<MetricCardsSkeleton />);
    expect(container.querySelectorAll('.animate-pulse').length).toBe(4);
  });

  it('EventFeedSkeleton renders 6 rows', () => {
    const { container } = render(<EventFeedSkeleton />);
    expect(container.querySelectorAll('.animate-pulse').length).toBe(6);
  });

  it('ScorecardGridSkeleton renders 8 rows', () => {
    const { container } = render(<ScorecardGridSkeleton />);
    // Single wrapper with animate-pulse containing 8 flex rows
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
    expect(container.querySelectorAll('.flex.gap-4').length).toBe(8);
  });

  it('EntityCardSkeleton renders 6 cards', () => {
    const { container } = render(<EntityCardSkeleton />);
    expect(container.querySelectorAll('.animate-pulse').length).toBe(6);
  });
});
