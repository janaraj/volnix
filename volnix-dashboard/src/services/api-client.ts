import type { Run, Entity, AgentSummary, World } from '@/types/domain';
import type {
  RunsListResponse, EventsListResponse, EventDetailResponse, EntitiesListResponse,
  GapsResponse, ScorecardResponse, DecisionTraceResponse, CompareResponse, WorldsListResponse,
  RunListParams, EventFilterParams, EntityFilterParams,
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
      const body = await response.json().catch(() => ({} as Record<string, unknown>));
      throw new ApiError(
        response.status,
        (body.code as string) ?? 'UNKNOWN',
        (body.message as string) ?? response.statusText,
        body.details,
      );
    }

    return (await response.json()) as T;
  }

  // ── Run endpoints ────────────────────────────
  async getRuns(params?: RunListParams): Promise<RunsListResponse> {
    return this.request('GET', '/api/v1/runs', params as Record<string, unknown>);
  }

  async getRun(id: string): Promise<Run> {
    return this.request('GET', `/api/v1/runs/${id}`);
  }

  // ── Deliverable endpoint ─────────────────────
  async getDeliverable(runId: string): Promise<Record<string, unknown>> {
    return this.request('GET', `/api/v1/runs/${runId}/deliverable`);
  }

  // ── Event endpoints ──────────────────────────
  async getRunEvents(runId: string, params?: EventFilterParams): Promise<EventsListResponse> {
    return this.request('GET', `/api/v1/runs/${runId}/events`, params as Record<string, unknown>);
  }

  async getRunEvent(runId: string, eventId: string): Promise<EventDetailResponse> {
    return this.request('GET', `/api/v1/runs/${runId}/events/${eventId}`);
  }

  // ── Scorecard ────────────────────────────────
  async getScorecard(runId: string): Promise<ScorecardResponse> {
    return this.request('GET', `/api/v1/runs/${runId}/scorecard`);
  }

  // ── Entity endpoints ─────────────────────────
  async getEntities(runId: string, params?: EntityFilterParams): Promise<EntitiesListResponse> {
    return this.request('GET', `/api/v1/runs/${runId}/entities`, params as Record<string, unknown>);
  }

  async getEntity(runId: string, entityId: string): Promise<Entity> {
    return this.request('GET', `/api/v1/runs/${runId}/entities/${entityId}`);
  }

  // ── Gaps ─────────────────────────────────────
  async getCapabilityGaps(runId: string): Promise<GapsResponse> {
    return this.request('GET', `/api/v1/runs/${runId}/gaps`);
  }

  // ── Decision Trace ───────────────────────────
  async getDecisionTrace(runId: string): Promise<DecisionTraceResponse> {
    return this.request('GET', `/api/v1/runs/${runId}/artifacts/decision_trace`);
  }

  // ── Actors ───────────────────────────────────
  async getActor(runId: string, actorId: string): Promise<AgentSummary> {
    return this.request('GET', `/api/v1/runs/${runId}/actors/${actorId}`);
  }

  // ── World endpoints ────────────────────────────
  async getWorlds(): Promise<WorldsListResponse> {
    return this.request('GET', '/api/v1/worlds');
  }

  async getWorld(worldId: string): Promise<World> {
    return this.request('GET', `/api/v1/worlds/${worldId}`);
  }

  // ── Run actions ──────────────────────────────
  async completeRun(runId: string): Promise<unknown> {
    return this.request('POST', `/api/v1/runs/${runId}/complete`);
  }

  async newRun(worldId?: string): Promise<{ run_id: string; world_id: string }> {
    return this.request('POST', '/api/v1/runs/new', worldId ? { world_id: worldId } : {});
  }

  // ── Comparison ───────────────────────────────
  async getComparison(runIds: string[]): Promise<CompareResponse> {
    return this.request('GET', '/api/v1/compare', { runs: runIds.join(',') });
  }
}
