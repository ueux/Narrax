/**
 * Shared API contract types.
 *
 * These mirror the backend response schemas (`backend/app/schemas/`). They are the single
 * place the frontend learns what the API returns; `lib/` turns them into requests and
 * `components/` render them.
 */

/**
 * Which epistemic layer a payload belongs to.
 *
 * The API labels every response so the UI can render AI interpretations differently from
 * ML observations and from source text (see docs/epistemic-layers.md, FR-15.2).
 */
export type EpistemicLayer = "source" | "observation" | "interpretation" | "temporal";

/** `GET /api/v1/health/live` — process liveness. */
export interface LivenessResponse {
  status: string;
}

/** `GET /api/v1/health/ready` — readiness, including a database probe. */
export interface ReadinessResponse {
  status: string;
  database: string;
}

/** Normalised shape used to construct an `ApiError` in `lib/api-client.ts`. */
export interface ApiErrorShape {
  /** HTTP status, or `0` when the request never reached the server. */
  status: number;
  message: string;
  detail?: unknown;
}
