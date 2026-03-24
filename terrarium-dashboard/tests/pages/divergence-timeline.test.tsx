import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DivergenceTimeline } from '@/pages/compare/divergence-timeline';
import type { DivergencePoint, Run } from '@/types/domain';
import { createMockRun } from '../mocks/data/runs';

const mockRuns: Run[] = [
  createMockRun({ id: 'run-1', tags: ['exp-1-baseline'] }),
  createMockRun({ id: 'run-2', tags: ['exp-2-variant'] }),
];

const mockPoints: DivergencePoint[] = [
  {
    tick: 4,
    timestamp: '2026-03-01T09:03:51Z',
    description: 'Refund attempt on $249 charge',
    decisions: { 'run-1': 'Escalated to supervisor', 'run-2': 'Retried without approval' },
    consequences: { 'run-1': 'Policy compliance maintained', 'run-2': 'Policy violation recorded' },
  },
];

describe('DivergenceTimeline', () => {
  it('renders nothing when no points', () => {
    const { container } = render(<DivergenceTimeline points={[]} runs={mockRuns} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders header and point description', () => {
    render(<DivergenceTimeline points={mockPoints} runs={mockRuns} />);
    expect(screen.getByText('Divergence Points')).toBeInTheDocument();
    expect(screen.getByText('Refund attempt on $249 charge')).toBeInTheDocument();
  });

  it('details are collapsed by default', () => {
    render(<DivergenceTimeline points={mockPoints} runs={mockRuns} />);
    expect(screen.queryByText('Escalated to supervisor')).not.toBeInTheDocument();
  });

  it('clicking header expands details', async () => {
    const user = userEvent.setup();
    render(<DivergenceTimeline points={mockPoints} runs={mockRuns} />);

    await user.click(screen.getByText('Refund attempt on $249 charge'));

    expect(screen.getByText(/Escalated to supervisor/)).toBeInTheDocument();
    expect(screen.getByText(/Retried without approval/)).toBeInTheDocument();
    expect(screen.getByText(/Policy compliance maintained/)).toBeInTheDocument();
  });

  it('clicking header again collapses details', async () => {
    const user = userEvent.setup();
    render(<DivergenceTimeline points={mockPoints} runs={mockRuns} />);

    await user.click(screen.getByText('Refund attempt on $249 charge'));
    expect(screen.getByText(/Escalated to supervisor/)).toBeInTheDocument();

    await user.click(screen.getByText('Refund attempt on $249 charge'));
    expect(screen.queryByText('Escalated to supervisor')).not.toBeInTheDocument();
  });
});
