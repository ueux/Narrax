"use client";

/**
 * Backend liveness hook.
 *
 * Owns the request lifecycle (loading → ok | error) and cleans up on unmount, so
 * components only render state.
 */

import { useEffect, useState } from "react";

import { fetchLiveness } from "@/lib/api";
import type { LivenessResponse } from "@/types/api";

export type HealthStatus = "loading" | "ok" | "error";

export interface UseHealthResult {
  status: HealthStatus;
  data: LivenessResponse | null;
  error: Error | null;
}

/** Probe the backend liveness endpoint once on mount. */
export function useHealth(): UseHealthResult {
  const [status, setStatus] = useState<HealthStatus>("loading");
  const [data, setData] = useState<LivenessResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let active = true;

    fetchLiveness()
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setStatus("ok");
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
        setStatus("error");
      });

    return () => {
      active = false;
    };
  }, []);

  return { status, data, error };
}
