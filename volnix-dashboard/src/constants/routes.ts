// ---------------------------------------------------------------------------
// Route constants and path builders
// ---------------------------------------------------------------------------

export const ROUTES = {
  RUN_LIST: '/',
  WORLDS: '/worlds',
  LIVE_CONSOLE: '/runs/:id/live',
  RUN_REPORT: '/runs/:id',
  COMPARE: '/compare',
} as const;

/** Build the path for a specific run report. */
export function runReportPath(id: string): string {
  return `/runs/${id}`;
}

/** Build the path for a live console of a running simulation. */
export function liveConsolePath(id: string): string {
  return `/runs/${id}/live`;
}

/** Build the compare page path with run IDs encoded as query params. */
export function comparePath(runIds: string[]): string {
  return `/compare?runs=${runIds.map(encodeURIComponent).join(',')}`;
}
