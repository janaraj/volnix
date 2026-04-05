import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TimestampCell } from '@/components/domain/timestamp-cell';

describe('TimestampCell', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders ISO timestamp as relative time', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-23T12:02:00Z'));

    render(<TimestampCell iso="2026-03-23T12:00:00Z" />);
    expect(screen.getByText('2 minutes ago')).toBeInTheDocument();
  });

  it('shows full timestamp on hover via title', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-23T12:02:00Z'));

    const { container } = render(<TimestampCell iso="2026-03-23T12:00:00Z" />);
    const span = container.querySelector('span[title]');
    expect(span).toBeInTheDocument();
    // date-fns format uses local timezone, so just verify the title contains a formatted date pattern
    expect(span!.getAttribute('title')).toMatch(/2026-03-23 \d{2}:00:00/);
  });
});
