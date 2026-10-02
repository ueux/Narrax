"use client";

import { useEffect, useState } from "react";

import { fetchHealth } from "@/lib/api";

type BackendStatus = "loading" | "ok" | "error";

export default function HealthCheck() {
  const [status, setStatus] = useState<BackendStatus>("loading");

  useEffect(() => {
    let active = true;
    fetchHealth()
      .then(() => {
        if (active) setStatus("ok");
      })
      .catch(() => {
        if (active) setStatus("error");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="status">
      Backend status:{" "}
      {status === "loading" && "checking…"}
      {status === "ok" && "connected"}
      {status === "error" && "unreachable"}
    </div>
  );
}
