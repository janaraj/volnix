import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';
import { ApiClient } from '@/services/api-client';
import { ApiError } from '@/types/api';

const api = new ApiClient('');

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ApiClient', () => {
  describe('getRuns', () => {
    it('fetches runs list from /api/runs', async () => {
      const result = await api.getRuns();
      expect(result.items).toHaveLength(3);
      expect(result.has_more).toBe(false);
    });

    it('passes filter params as query string', async () => {
      let capturedUrl = '';
      server.use(
        http.get('/api/runs', ({ request }) => {
          capturedUrl = request.url;
          return HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0, has_more: false });
        }),
      );
      await api.getRuns({ status: 'running', limit: 10 });
      expect(capturedUrl).toContain('status=running');
      expect(capturedUrl).toContain('limit=10');
    });

    it('throws ApiError on non-OK response', async () => {
      server.use(
        http.get('/api/runs', () =>
          HttpResponse.json({ code: 'BAD_REQUEST', message: 'Invalid' }, { status: 400 }),
        ),
      );
      await expect(api.getRuns()).rejects.toThrow(ApiError);
    });
  });

  describe('getRun', () => {
    it('fetches single run by id', async () => {
      const result = await api.getRun('run-test-001');
      expect(result.id).toBe('run-test-001');
      expect(result.world_name).toBeDefined();
    });
  });

  describe('getRunEvents', () => {
    it('fetches paginated events for a run', async () => {
      const result = await api.getRunEvents('run-test-001');
      expect(result.items.length).toBeGreaterThan(0);
    });

    it('passes filter params', async () => {
      let capturedUrl = '';
      server.use(
        http.get('/api/runs/:id/events', ({ request }) => {
          capturedUrl = request.url;
          return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0, has_more: false });
        }),
      );
      await api.getRunEvents('run-1', { actor_id: 'agent-alpha' });
      expect(capturedUrl).toContain('actor_id=agent-alpha');
    });
  });

  describe('getScorecard', () => {
    it('fetches scorecard for a run', async () => {
      const result = await api.getScorecard('run-1');
      expect(Array.isArray(result)).toBe(true);
      expect(result[0].overall_score).toBe(0.9);
    });
  });

  describe('error handling', () => {
    it('normalizes 404 to ApiError', async () => {
      server.use(
        http.get('/api/runs/:id', () =>
          HttpResponse.json({ code: 'NOT_FOUND', message: 'Not found' }, { status: 404 }),
        ),
      );
      try {
        await api.getRun('missing');
        expect.fail('should have thrown');
      } catch (e) {
        expect(e).toBeInstanceOf(ApiError);
        expect((e as ApiError).status).toBe(404);
      }
    });

    it('normalizes 500 to ApiError', async () => {
      server.use(
        http.get('/api/runs/:id', () =>
          HttpResponse.json({ code: 'INTERNAL', message: 'Server error' }, { status: 500 }),
        ),
      );
      await expect(api.getRun('any')).rejects.toMatchObject({ status: 500 });
    });

    it('normalizes network errors', async () => {
      server.use(
        http.get('/api/runs/:id', () => HttpResponse.error()),
      );
      await expect(api.getRun('any')).rejects.toThrow();
    });
  });
});
