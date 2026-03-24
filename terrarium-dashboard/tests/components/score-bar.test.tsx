import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ScoreBar } from '@/components/domain/score-bar';

describe('ScoreBar', () => {
  it('renders value without formula', () => {
    render(<ScoreBar value={0.85} />);
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('renders label when provided', () => {
    render(<ScoreBar value={0.7} label="Compliance" />);
    expect(screen.getByText('Compliance')).toBeInTheDocument();
  });

  it('shows formula in title on hover when provided', () => {
    const { container } = render(<ScoreBar value={0.94} formula="(actions - violations) / actions" />);
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.getAttribute('title')).toBe('94 — (actions - violations) / actions');
  });

  it('does not show title when no formula', () => {
    const { container } = render(<ScoreBar value={0.5} />);
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.getAttribute('title')).toBeNull();
  });
});
