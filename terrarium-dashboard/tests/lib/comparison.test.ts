import { describe, it, expect } from 'vitest';
import { findBestValue, computeMetricDelta } from '@/lib/comparison';

describe('findBestValue', () => {
  it('returns run_id with highest value when higherIsBetter', () => {
    expect(findBestValue({ a: 90, b: 80 }, true)).toBe('a');
  });
  it('returns run_id with lowest value when not higherIsBetter', () => {
    expect(findBestValue({ a: 90, b: 80 }, false)).toBe('b');
  });
  it('returns null for empty values', () => {
    expect(findBestValue({})).toBeNull();
  });
  it('handles single entry', () => {
    expect(findBestValue({ only: 42 })).toBe('only');
  });
  it('defaults to higherIsBetter', () => {
    expect(findBestValue({ a: 10, b: 20 })).toBe('b');
  });
});

describe('computeMetricDelta', () => {
  it('computes positive delta', () => {
    const result = computeMetricDelta(80, 90);
    expect(result.delta).toBe(10);
    expect(result.improved).toBe(true);
  });
  it('computes negative delta', () => {
    const result = computeMetricDelta(90, 80);
    expect(result.delta).toBe(-10);
    expect(result.improved).toBe(false);
  });
  it('handles equal values', () => {
    const result = computeMetricDelta(50, 50);
    expect(result.delta).toBe(0);
    expect(result.improved).toBe(false);
  });
});
