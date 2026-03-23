import type {
  Run, WorldEvent, Entity, AgentSummary,
  GovernanceScorecard, CapabilityGap, RunComparison,
} from '@/types/domain';
import type {
  PaginatedResponse, RunListParams, EventFilterParams,
  EntityFilterParams,
} from '@/types/api';
import { ApiError } from '@/types/api';

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = '') {
    this.baseUrl = baseUrl;
  }

  // Generic request helper
  private async request<T>(method: string, path: string, params?: Record<string, unknown>): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    if (method === 'GET' && params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.set(key, String(value));
        }
      });
      const qs = searchParams.toString();
      if (qs) url += `?${qs}`;
    }

    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      ...(method !== 'GET' && params ? { body: JSON.stringify(params) } : {}),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(
        response.status,
        body.code ?? 'UNKNOWN',
        body.message ?? response.statusText,
        body.details,
      );
    }

    return response.json() as Promise<T>;
  }

  // ── Run endpoints ────────────────────────────
  async getRuns(params?: RunListParams): Promise<PaginatedResponse<Run>> {
    return this.request('GET', '/api/runs', params as Record<string, unknown>);
  }

  async getRun(id: string): Promise<Run> {
    return this.request('GET', `/api/runs/${id}`);
  }

  // ── Event endpoints ──────────────────────────
  async getRunEvents(runId: string, params?: EventFilterParams): Promise<PaginatedResponse<WorldEvent>> {
    return this.request('GET', `/api/runs/${runId}/events`, params as Record<string, unknown>);
  }

  async getRunEvent(runId: string, eventId: string): Promise<WorldEvent> {
    return this.request('GET', `/api/runs/${runId}/events/${eventId}`);
  }

  // ── Scorecard ────────────────────────────────
  async getScorecard(runId: string): Promise<GovernanceScorecard[]> {
    return this.request('GET', `/api/runs/${runId}/scorecard`);
  }

  // ── Entity endpoints ─────────────────────────
  async getEntities(runId: string, params?: EntityFilterParams): Promise<PaginatedResponse<Entity>> {
    return this.request('GET', `/api/runs/${runId}/entities`, params as Record<string, unknown>);
  }

  async getEntity(runId: string, entityId: string): Promise<Entity> {
    return this.request('GET', `/api/runs/${runId}/entities/${entityId}`);
  }

  // ── Gaps ─────────────────────────────────────
  async getCapabilityGaps(runId: string): Promise<CapabilityGap[]> {
    return this.request('GET', `/api/runs/${runId}/gaps`);
  }

  // ── Actors ───────────────────────────────────
  async getActor(runId: string, actorId: string): Promise<AgentSummary> {
    return this.request('GET', `/api/runs/${runId}/actors/${actorId}`);
  }

  // ── Comparison ───────────────────────────────
  async getComparison(runIds: string[]): Promise<RunComparison> {
    return this.request('GET', '/api/compare', { runs: runIds.join(',') });
  }
}
