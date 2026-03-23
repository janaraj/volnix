import { describe, it, expect } from 'vitest';
import { computeGrade, normalizeScore } from '@/lib/score-utils';

describe('computeGrade', () => {
  it('returns A with score-excellent for >= 0.9', () => {
    const grade = computeGrade(0.95);
    expect(grade.label).toBe('A');
    expect(grade.colorClass).toContain('score-excellent');
  });
  it('returns B with score-good for >= 0.75', () => {
    const grade = computeGrade(0.80);
    expect(grade.label).toBe('B');
    expect(grade.colorClass).toContain('score-good');
  });
  it('returns C with score-fair for >= 0.6', () => {
    const grade = computeGrade(0.65);
    expect(grade.label).toBe('C');
    expect(grade.colorClass).toContain('score-fair');
  });
  it('returns D with score-poor for < 0.6', () => {
    const grade = computeGrade(0.3);
    expect(grade.label).toBe('D');
    expect(grade.colorClass).toContain('score-poor');
  });
  it('handles exact boundary 0.9', () => { expect(computeGrade(0.9).label).toBe('A'); });
});

describe('normalizeScore', () => {
  it('returns value unchanged for default 0-1 range', () => { expect(normalizeScore(0.5)).toBe(0.5); });
  it('normalizes from custom range', () => { expect(normalizeScore(50, 0, 100)).toBe(0.5); });
  it('clamps below min to 0', () => { expect(normalizeScore(-1)).toBe(0); });
  it('clamps above max to 1', () => { expect(normalizeScore(2)).toBe(1); });
  it('returns 0 when min equals max', () => { expect(normalizeScore(5, 5, 5)).toBe(0); });
});
