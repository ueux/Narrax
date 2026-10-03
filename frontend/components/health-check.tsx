"use client";

import { useHealth, type HealthStatus } from "@/hooks/use-health";

const STATUS_LABELS: Record<HealthStatus, string> = {
  loading: "checking…",
  ok: "connected",
  error: "unreachable",
};

export default function HealthCheck() {
  const { status } = useHealth();

  return <div className="status">Backend status: {STATUS_LABELS[status]}</div>;
}
