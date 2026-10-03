/**
 * Low-level typed HTTP client for the NarraX backend.
 *
 * This is the only module that knows the API base URL or calls `fetch`. It normalises both
 * transport failures and non-2xx responses into a single `ApiError`, so callers never have
 * to reason about `Response` objects.
 */

import type { ApiErrorShape } from "@/types/api";

/**
 * Base URL of the backend API.
 *
 * `NEXT_PUBLIC_*` values are inlined by Next.js at build time and are therefore public —
 * never place secrets in one.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Error thrown by {@link apiFetch} for any failed request. */
export class ApiError extends Error {
  /** HTTP status code, or `0` if the request never reached the server. */
  readonly status: number;
  /** Parsed error body when the server returned one. */
  readonly detail: unknown;

  constructor({ status, message, detail }: ApiErrorShape) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Read a response body without failing if it is empty or not JSON. */
async function readDetail(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

/**
 * Perform a JSON request against the backend and return the typed payload.
 *
 * @throws {ApiError} on network failure or a non-2xx response.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (cause) {
    throw new ApiError({
      status: 0,
      message: `Network request to ${url} failed`,
      detail: cause,
    });
  }

  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      message: `Request to ${path} failed with status ${response.status}`,
      detail: await readDetail(response),
    });
  }

  return (await response.json()) as T;
}
