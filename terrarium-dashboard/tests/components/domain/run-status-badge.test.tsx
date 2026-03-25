import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RunStatusBadge } from '@/components/domain/run-status-badge';

describe('RunStatusBadge', () => {
  it('renders correct color for each status', () => {
    const { container } = render(<RunStatusBadge status="running" />);
    const badge = container.firstElementChild;
    expect(badge).toHaveClass('text-info');
  });

  it('shows capitalized status text', () => {
    render(<RunStatusBadge status="running" />);
    expect(screen.getByText('Running')).toBeInTheDocument();
  });

  it('renders completed status', () => {
    render(<RunStatusBadge status="completed" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('applies spin animation for running status', () => {
    const { container } = render(<RunStatusBadge status="running" />);
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  it('does not apply spin animation for non-running status', () => {
    const { container } = render(<RunStatusBadge status="completed" />);
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).not.toBeInTheDocument();
  });
});
