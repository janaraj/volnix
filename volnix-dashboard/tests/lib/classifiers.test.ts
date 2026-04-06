import { describe, it, expect } from 'vitest';
import {
  eventTypeToColorClass, outcomeToColorClass, enforcementToColorClass,
  gapResponseToLabel, runStatusToColorClass, scoreToGradeLabel,
} from '@/lib/classifiers';

describe('eventTypeToColorClass', () => {
  it('maps agent_action to info', () => { expect(eventTypeToColorClass('agent_action')).toBe('text-info'); });
  it('maps policy_block to error', () => { expect(eventTypeToColorClass('policy_block')).toBe('text-error'); });
  it('maps policy_hold to warning', () => { expect(eventTypeToColorClass('policy_hold')).toBe('text-warning'); });
  it('maps animator_event to info', () => { expect(eventTypeToColorClass('animator_event')).toBe('text-info'); });
  it('maps budget_exhausted to error', () => { expect(eventTypeToColorClass('budget_exhausted')).toBe('text-error'); });
  it('returns fallback for unknown', () => { expect(eventTypeToColorClass('xyz')).toBe('text-text-muted'); });
});

describe('outcomeToColorClass', () => {
  it('maps success', () => { expect(outcomeToColorClass('success')).toBe('text-success'); });
  it('maps denied', () => { expect(outcomeToColorClass('denied')).toBe('text-error'); });
  it('maps held', () => { expect(outcomeToColorClass('held')).toBe('text-warning'); });
  it('maps flagged', () => { expect(outcomeToColorClass('flagged')).toBe('text-info'); });
  it('maps gap', () => { expect(outcomeToColorClass('gap')).toBe('text-neutral'); });
  it('returns fallback for unknown', () => { expect(outcomeToColorClass('xyz')).toBe('text-text-muted'); });
});

describe('enforcementToColorClass', () => {
  it('maps hold', () => { expect(enforcementToColorClass('hold')).toBe('text-warning'); });
  it('maps block', () => { expect(enforcementToColorClass('block')).toBe('text-error'); });
  it('maps escalate', () => { expect(enforcementToColorClass('escalate')).toBe('text-warning'); });
  it('maps log', () => { expect(enforcementToColorClass('log')).toBe('text-text-muted'); });
  it('returns fallback for unknown', () => { expect(enforcementToColorClass('xyz')).toBe('text-text-muted'); });
});

describe('gapResponseToLabel', () => {
  it('maps hallucinated', () => { expect(gapResponseToLabel('hallucinated')).toBe('Hallucinated'); });
  it('maps adapted', () => { expect(gapResponseToLabel('adapted')).toBe('Adapted'); });
  it('maps escalated', () => { expect(gapResponseToLabel('escalated')).toBe('Escalated'); });
  it('maps skipped', () => { expect(gapResponseToLabel('skipped')).toBe('Skipped'); });
  it('returns raw input for unknown', () => { expect(gapResponseToLabel('xyz')).toBe('xyz'); });
});

describe('runStatusToColorClass', () => {
  it('maps running', () => { expect(runStatusToColorClass('running')).toBe('text-info'); });
  it('maps completed', () => { expect(runStatusToColorClass('completed')).toBe('text-success'); });
  it('maps failed', () => { expect(runStatusToColorClass('failed')).toBe('text-error'); });
  it('maps stopped', () => { expect(runStatusToColorClass('stopped')).toBe('text-warning'); });
  it('returns fallback for unknown', () => { expect(runStatusToColorClass('xyz')).toBe('text-text-muted'); });
});

describe('scoreToGradeLabel', () => {
  it('returns A for >= 0.9', () => { expect(scoreToGradeLabel(0.95)).toBe('A'); });
  it('returns B for >= 0.75', () => { expect(scoreToGradeLabel(0.80)).toBe('B'); });
  it('returns C for >= 0.6', () => { expect(scoreToGradeLabel(0.65)).toBe('C'); });
  it('returns D for < 0.6', () => { expect(scoreToGradeLabel(0.3)).toBe('D'); });
  it('handles boundary 0.9', () => { expect(scoreToGradeLabel(0.9)).toBe('A'); });
  it('handles boundary 0.75', () => { expect(scoreToGradeLabel(0.75)).toBe('B'); });
});
