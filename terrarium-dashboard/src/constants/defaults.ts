// ---------------------------------------------------------------------------
// Application-wide default values
// ---------------------------------------------------------------------------

// TanStack Query stale times (ms)
export const STALE_TIME_RUNS_LIST = 30_000;
export const STALE_TIME_RUN_DETAIL = 60_000;
export const STALE_TIME_EVENTS = 60_000;
export const STALE_TIME_SCORECARD = Infinity; // completed run scorecard never changes
export const STALE_TIME_ENTITIES = 60_000;
export const STALE_TIME_COMPARISON = Infinity;

// Pagination
export const PAGE_SIZE_RUNS = 20;
export const PAGE_SIZE_EVENTS = 50;
export const PAGE_SIZE_ENTITIES = 50;

// UI
export const DEBOUNCE_MS_SEARCH = 300;
export const DEBOUNCE_MS_FILTER = 200;

// WebSocket
export const WS_RECONNECT_BASE_MS = 1_000;
export const WS_RECONNECT_MAX_MS = 30_000;
export const WS_RECONNECT_MULTIPLIER = 2;
