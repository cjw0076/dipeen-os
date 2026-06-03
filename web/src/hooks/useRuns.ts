"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ControlPlaneRun } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export function useRuns(taskId?: string) {
  const [runs, setRuns] = useState<ControlPlaneRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.runs.list({ taskId, limit: 100 });
      setRuns(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useEffect(() => {
    const handler = (event: WSEvent) => {
      const eventTaskId = event.task_id as string | undefined;
      if (!taskId || !eventTaskId || eventTaskId === taskId) void refetch();
    };
    wsManager.on("run.updated", handler);
    wsManager.on("task_update", handler);
    return () => {
      wsManager.off("run.updated", handler);
      wsManager.off("task_update", handler);
    };
  }, [refetch, taskId]);

  return { runs, loading, error, refetch };
}
