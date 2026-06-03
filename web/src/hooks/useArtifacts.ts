"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ControlPlaneArtifact } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export function useArtifacts(opts: { taskId?: string; runId?: string; type?: string } = {}) {
  const { taskId, runId, type } = opts;
  const [artifacts, setArtifacts] = useState<ControlPlaneArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.artifacts.list({ taskId, runId, type });
      setArtifacts(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [taskId, runId, type]);

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
    wsManager.on("artifact.created", handler);
    wsManager.on("artifact.verified", handler);
    return () => {
      wsManager.off("artifact.created", handler);
      wsManager.off("artifact.verified", handler);
    };
  }, [refetch, taskId, runId]);

  return { artifacts, loading, error, refetch };
}
