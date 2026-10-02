export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface LivenessResponse {
  status: string;
}

/** Fetch the backend liveness probe. */
export async function fetchHealth(): Promise<LivenessResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health/live`);
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }
  return (await response.json()) as LivenessResponse;
}
