import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  formatRelativeTime, formatDuration, formatCurrency,
  formatScore, formatPercentage, formatTick, truncateId,
} from '@/lib/formatters';

describe('formatRelativeTime', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('returns relative time for recent dates', () => {
    vi.setSystemTime(new Date('2026-03-01T10:00:00Z'));
    expect(formatRelativeTime('2026-03-01T09:58:00Z')).toBe('2 minutes ago');
  });

  it('returns formatted date for dates older than 24h', () => {
    vi.setSystemTime(new Date('2026-03-02T10:00:00Z'));
    const result = formatRelativeTime('2026-03-01T09:00:00Z');
    expect(result).toMatch(/Mar 1/);
  });

  it('returns raw input for invalid dates', () => {
    expect(formatRelativeTime('not-a-date')).toBe('not-a-date');
  });
});

describe('formatDuration', () => {
  it('formats sub-second as ms', () => { expect(formatDuration(500)).toBe('500ms'); });
  it('formats seconds', () => { expect(formatDuration(5000)).toBe('5s'); });
  it('formats minutes and seconds', () => { expect(formatDuration(65000)).toBe('1m 5s'); });
  it('formats hours minutes seconds', () => { expect(formatDuration(3661000)).toBe('1h 1m 1s'); });
  it('formats exact minutes omitting zero seconds', () => { expect(formatDuration(60000)).toBe('1m'); });
  it('handles zero', () => { expect(formatDuration(0)).toBe('0ms'); });
});

describe('formatCurrency', () => {
  it('formats dollars', () => { expect(formatCurrency(3.42)).toBe('$3.42'); });
  it('formats zero', () => { expect(formatCurrency(0)).toBe('$0.00'); });
  it('rounds to two decimals', () => { expect(formatCurrency(1.999)).toBe('$2.00'); });
});

describe('formatScore', () => {
  it('converts 0.87 to "87"', () => { expect(formatScore(0.87)).toBe('87'); });
  it('handles 0', () => { expect(formatScore(0)).toBe('0'); });
  it('handles 1', () => { expect(formatScore(1)).toBe('100'); });
});

describe('formatPercentage', () => {
  it('converts 0.87 to "87%"', () => { expect(formatPercentage(0.87)).toBe('87%'); });
  it('handles 0', () => { expect(formatPercentage(0)).toBe('0%'); });
});

describe('formatTick', () => {
  it('prepends hash', () => { expect(formatTick(234)).toBe('#234'); });
  it('handles zero', () => { expect(formatTick(0)).toBe('#0'); });
});

describe('truncateId', () => {
  it('truncates to 8 by default', () => { expect(truncateId('abcdefghijklmnop')).toBe('abcdefgh'); });
  it('truncates to custom length', () => { expect(truncateId('abcdefghijklmnop', 4)).toBe('abcd'); });
  it('returns full string when shorter than length', () => { expect(truncateId('abc')).toBe('abc'); });
});
