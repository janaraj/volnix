import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ScoreBar } from '@/components/domain/score-bar';

describe('ScoreBar', () => {
  it('renders score as percentage width', () => {
    const { container } = render(<ScoreBar value={0.75} />);
    const bar = container.querySelector('[style]');
    expect(bar).toHaveStyle({ width: '75%' });
  });

  it('displays numeric value', () => {
    render(<ScoreBar value={0.75} />);
    expect(screen.getByText('75')).toBeInTheDocument();
  });

  it('shows label when provided', () => {
    render(<ScoreBar value={0.5} label="Accuracy" />);
    expect(screen.getByText('Accuracy')).toBeInTheDocument();
  });

  it('does not render label span when label is not provided', () => {
    const { container } = render(<ScoreBar value={0.5} />);
    const spans = container.querySelectorAll('span');
    // Only the numeric value span should exist, no label span
    expect(spans).toHaveLength(1);
  });
});
