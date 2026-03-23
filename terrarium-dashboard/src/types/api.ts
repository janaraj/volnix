// ---------------------------------------------------------------------------
// API request / response types
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface RunListParams {
  status?: string;
  preset?: string;
  from_date?: string;
  to_date?: string;
  tag?: string;
  limit?: number;
  offset?: number;
  sort?: string;
}

export interface EventFilterParams {
  actor_id?: string;
  service_id?: string;
  event_type?: string;
  outcome?: string;
  tick_from?: number;
  tick_to?: number;
  limit?: number;
  offset?: number;
}

export interface EntityFilterParams {
  entity_type?: string;
  service_id?: string;
  limit?: number;
  offset?: number;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
