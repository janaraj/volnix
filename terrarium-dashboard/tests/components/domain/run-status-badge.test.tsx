import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RunStatusBadge } from '@/components/domain/run-status-badge';

describe('RunStatusBadge', () => {
  it('renders correct color for each status', () => {
    const { container } = render(<RunStatusBadge status="running" />);
    const badge = container.firstElementChild;
    expect(badge).toHaveClass('text-info');
  });

  it('shows status text', () => {
    render(<RunStatusBadge status="running" />);
    expect(screen.getByText('running')).toBeInTheDocument();
  });

  it('renders completed status', () => {
    render(<RunStatusBadge status="completed" />);
    expect(screen.getByText('completed')).toBeInTheDocument();
  });

  it('applies pulse animation for running status', () => {
    const { container } = render(<RunStatusBadge status="running" />);
    const dot = container.querySelector('.animate-pulse');
    expect(dot).toBeInTheDocument();
  });

  it('does not apply pulse animation for non-running status', () => {
    const { container } = render(<RunStatusBadge status="completed" />);
    const dot = container.querySelector('.animate-pulse');
    expect(dot).not.toBeInTheDocument();
  });
});
