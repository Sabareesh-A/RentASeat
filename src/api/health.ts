import { request } from './client';

// Shape returned by the Lambda GET /health handler.
export interface HealthResponse {
  status: string;
  service?: string;
  message?: string;
  timestamp?: string;
  [key: string]: unknown; // allow extra fields without breaking the type
}

/**
 * Calls GET /health on the API Gateway.
 * Returns the parsed response body.
 */
export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}
