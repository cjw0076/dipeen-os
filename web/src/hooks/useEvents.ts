"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ControlPlaneEvent } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export function useEvents(opts: { taskId?: string; runId?: string; tail?: number } = {}) {
  const { taskId, runId, tail = 100 } = opts;
  const [events, setEvents] = useState<ControlPlaneEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.events.list({ taskId, runId, tail });
      setEvents(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [taskId, runId, tail]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useEffect(() => {
    const handler = (event: WSEvent) => {
      const eventTaskId = event.task_id as string | undefined;
      const eventRunId = event.run_id as string | undefined;
      if (taskId && eventTaskId && eventTaskId !== taskId) return;
      if (runId && eventRunId && eventRunId !== runId) return;
      void refetch();
    };
    wsManager.on("event.created", handler);
    wsManager.on("run.updated", handler);
    return () => {
      wsManager.off("event.created", handler);
      wsManager.off("run.updated", handler);
    };
  }, [refetch, taskId, runId]);

  return { events, loading, error, refetch };
}
