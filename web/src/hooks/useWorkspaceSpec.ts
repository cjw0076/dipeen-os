"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type TeamWorkspaceSpec } from "@/lib/api";
import { wsManager } from "@/lib/ws";

const INVALIDATION_EVENTS = [
  "workspace.spec_updated",
  "workspace.applied",
];

export function useWorkspaceSpec() {
  const [spec, setSpec] = useState<TeamWorkspaceSpec | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.workspace.spec();
      setSpec(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
    const timer = setInterval(refetch, 30_000);
    return () => clearInterval(timer);
  }, [refetch]);

  useEffect(() => {
    const handler = () => void refetch();
    for (const eventType of INVALIDATION_EVENTS) wsManager.on(eventType, handler);
    return () => {
      for (const eventType of INVALIDATION_EVENTS) wsManager.off(eventType, handler);
    };
  }, [refetch]);

  return { spec, loading, error, refetch };
}
