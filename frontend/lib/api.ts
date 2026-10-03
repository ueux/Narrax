/**
 * Domain API functions.
 *
 * One thin, typed function per backend endpoint, built on the shared client
 * (`lib/api-client.ts`). Components and hooks call these, never `fetch` directly.
 */

import { apiFetch } from "@/lib/api-client";
import type { LivenessResponse, ReadinessResponse } from "@/types/api";

/** Backend liveness probe. */
export function fetchLiveness(): Promise<LivenessResponse> {
  return apiFetch<LivenessResponse>("/api/v1/health/live");
}

/** Backend readiness probe (includes a database connectivity check). */
export function fetchReadiness(): Promise<ReadinessResponse> {
  return apiFetch<ReadinessResponse>("/api/v1/health/ready");
}
