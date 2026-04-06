import { describe, it, expect } from 'vitest';
import { scoreToColorClass, interpolateScoreColor } from '@/lib/color-utils';

describe('scoreToColorClass', () => {
  it('returns score-excellent for >= 0.9', () => { expect(scoreToColorClass(0.95)).toContain('score-excellent'); });
  it('returns score-good for >= 0.75', () => { expect(scoreToColorClass(0.80)).toContain('score-good'); });
  it('returns score-fair for >= 0.6', () => { expect(scoreToColorClass(0.65)).toContain('score-fair'); });
  it('returns score-poor for < 0.6', () => { expect(scoreToColorClass(0.3)).toContain('score-poor'); });
  it('handles boundary 0.9', () => { expect(scoreToColorClass(0.9)).toContain('score-excellent'); });
  it('includes both bg and text classes', () => {
    const cls = scoreToColorClass(0.95);
    expect(cls).toContain('bg-');
    expect(cls).toContain('text-');
  });
});

describe('interpolateScoreColor', () => {
  it('returns valid hex string', () => { expect(interpolateScoreColor(0.5)).toMatch(/^#[0-9a-f]{6}$/); });
  it('returns reddish for low scores', () => {
    const hex = interpolateScoreColor(0);
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    expect(r).toBeGreaterThan(g);
  });
  it('returns greenish for high scores', () => {
    const hex = interpolateScoreColor(1);
    const g = parseInt(hex.slice(3, 5), 16);
    const r = parseInt(hex.slice(1, 3), 16);
    expect(g).toBeGreaterThan(r);
  });
  it('clamps values above 1', () => { expect(interpolateScoreColor(1.5)).toMatch(/^#[0-9a-f]{6}$/); });
  it('clamps values below 0', () => { expect(interpolateScoreColor(-0.5)).toMatch(/^#[0-9a-f]{6}$/); });
});
