/**
 * RentASeat API client
 *
 * Reads the base URL from the VITE_API_URL environment variable.
 * All requests go through the `request` function so future concerns
 * (auth headers, token refresh, request IDs) can be added in one place.
 *
 * NOTE: Do NOT hardcode the API Gateway URL here or in any component.
 *       Set VITE_API_URL in .env.local for local development.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL as string | undefined;

if (!API_BASE_URL) {
  // Warn loudly in development; in production a missing env var is a deploy error.
  console.warn(
    '[api/client] VITE_API_URL is not set. ' +
      'Create a .env.local file with VITE_API_URL=<your API Gateway URL>.'
  );
}

// ─── Typed API error ────────────────────────────────────────────────────────

export class ApiError extends Error {
  readonly status: number;
  readonly body?: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

// ─── Core request helper ────────────────────────────────────────────────────

/**
 * Makes an HTTP request to the RentASeat API.
 *
 * @param path   - API path, e.g. '/health'  (leading slash required)
 * @param init   - Standard RequestInit options (method, headers, body, etc.)
 * @returns      - Parsed JSON response body typed as T
 * @throws       - ApiError for non-2xx responses
 * @throws       - TypeError for network failures (no connectivity, DNS, CORS)
 */
export async function request<T = unknown>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError(0, 'API base URL is not configured (VITE_API_URL missing).');
  }

  const url = `${API_BASE_URL.replace(/\/$/, '')}${path}`;

  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      // Future: add Authorization header here once JWT auth is implemented.
      ...init.headers,
    },
  });

  // Attempt to parse JSON regardless of status so error bodies are available.
  let body: unknown;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    body = await response.json();
  } else {
    body = await response.text();
  }

  if (!response.ok) {
    const message =
      typeof body === 'object' && body !== null && 'message' in body
        ? String((body as Record<string, unknown>).message)
        : `HTTP ${response.status} ${response.statusText}`;
    throw new ApiError(response.status, message, body);
  }

  return body as T;
}
