import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { OutcomeIcon } from '@/components/domain/outcome-icon';

describe('OutcomeIcon', () => {
  it('renders check for success', () => {
    render(<OutcomeIcon outcome="success" />);
    expect(screen.getByLabelText('success')).toBeInTheDocument();
  });

  it('renders X for denied', () => {
    render(<OutcomeIcon outcome="denied" />);
    expect(screen.getByLabelText('denied')).toBeInTheDocument();
  });

  it('renders warning for held', () => {
    render(<OutcomeIcon outcome="held" />);
    expect(screen.getByLabelText('held')).toBeInTheDocument();
  });

  it('renders default for unknown outcome', () => {
    // Should not crash, falls back to Circle icon
    render(<OutcomeIcon outcome={'unknown' as unknown as import('@/types/domain').Outcome} />);
    expect(screen.getByLabelText('unknown')).toBeInTheDocument();
  });
});
