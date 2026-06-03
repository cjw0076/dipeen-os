"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type StateClaim } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export function useStateClaims(opts: { taskId?: string; runId?: string } = {}) {
  const { taskId, runId } = opts;
  const [claims, setClaims] = useState<StateClaim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.stateClaims.list({ taskId, runId });
      setClaims(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [taskId, runId]);

  useEffect(() => {
    refetch();
    const timer = setInterval(refetch, 30_000);
    return () => clearInterval(timer);
  }, [refetch]);

  useEffect(() => {
    const handler = (event: WSEvent) => {
      const eventTaskId = event.task_id as string | undefined;
      const eventRunId = event.run_id as string | undefined;
      if (taskId && eventTaskId && eventTaskId !== taskId) return;
      if (runId && eventRunId && eventRunId !== runId) return;
      void refetch();
    };
    wsManager.on("state.claimed", handler);
    wsManager.on("state.reconciled", handler);
    wsManager.on("event.created", handler);
    return () => {
      wsManager.off("state.claimed", handler);
      wsManager.off("state.reconciled", handler);
      wsManager.off("event.created", handler);
    };
  }, [refetch, taskId, runId]);

  return { claims, loading, error, refetch };
}
