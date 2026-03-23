import { describe, it } from 'vitest';

describe('ApiClient', () => {
  describe('getRuns', () => {
    it.todo('fetches runs list from /api/runs');
    it.todo('passes filter params as query string');
    it.todo('throws ApiError on non-OK response');
  });

  describe('getRun', () => {
    it.todo('fetches single run by id');
  });

  describe('getRunEvents', () => {
    it.todo('fetches paginated events for a run');
    it.todo('passes filter params');
  });

  describe('getScorecard', () => {
    it.todo('fetches scorecard for a run');
  });

  describe('error handling', () => {
    it.todo('normalizes 404 to ApiError');
    it.todo('normalizes 500 to ApiError');
    it.todo('normalizes network errors');
  });
});
