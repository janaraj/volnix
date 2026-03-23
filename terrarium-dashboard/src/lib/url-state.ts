// ---------------------------------------------------------------------------
// URL search-param serialization helpers
// ---------------------------------------------------------------------------

/**
 * Serialize a params object into a URLSearchParams instance, omitting
 * undefined values.
 *
 * @param params - Key-value pairs to serialize
 * @returns URLSearchParams instance
 */
export function serializeParams(
  params: Record<string, string | number | undefined>,
): URLSearchParams {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      searchParams.set(key, String(value));
    }
  }
  return searchParams;
}

/**
 * Deserialize a URLSearchParams instance into a plain object of string values.
 *
 * @param search - URLSearchParams to deserialize
 * @returns Plain object with string values
 */
export function deserializeParams(search: URLSearchParams): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of search.entries()) {
    result[key] = value;
  }
  return result;
}
