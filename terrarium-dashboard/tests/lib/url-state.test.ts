import { describe, it, expect } from 'vitest';
import { serializeParams, deserializeParams } from '@/lib/url-state';

describe('serializeParams', () => {
  it('serializes string values', () => {
    const params = serializeParams({ status: 'running', tag: 'exp-1' });
    expect(params.get('status')).toBe('running');
    expect(params.get('tag')).toBe('exp-1');
  });
  it('serializes numeric values as strings', () => {
    const params = serializeParams({ limit: 50 });
    expect(params.get('limit')).toBe('50');
  });
  it('omits undefined values', () => {
    const params = serializeParams({ a: 'yes', b: undefined });
    expect(params.has('a')).toBe(true);
    expect(params.has('b')).toBe(false);
  });
  it('handles empty params', () => {
    const params = serializeParams({});
    expect(params.toString()).toBe('');
  });
});

describe('deserializeParams', () => {
  it('converts URLSearchParams to plain object', () => {
    const search = new URLSearchParams('a=1&b=hello');
    expect(deserializeParams(search)).toEqual({ a: '1', b: 'hello' });
  });
  it('handles empty search params', () => {
    expect(deserializeParams(new URLSearchParams())).toEqual({});
  });
  it('preserves all key-value pairs', () => {
    const search = new URLSearchParams('x=1&y=2&z=3');
    const result = deserializeParams(search);
    expect(Object.keys(result)).toHaveLength(3);
  });
});
