"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ControlPlaneSummary } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

const INVALIDATION_EVENTS = [
  "run.updated",
  "event.created",
  "artifact.created",
  "artifact.verified",
  "permission.requested",
  "permission.updated",
  "permission.executed",
  "memory.candidate_created",
  "memory.candidate_updated",
  "decision_created",
  "decision_updated",
  "message.created",
  "proposal.created",
  "proposal.rejected",
  "command.queued",
  "command.leased",
  "command.running",
  "command.completed",
  "command.failed",
  "worker.updated",
  "task_update",
  "agent_status",
];

export function useControlPlaneSummary() {
  const [summary, setSummary] = useState<ControlPlaneSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.controlPlane.summary();
      setSummary(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
    const timer = setInterval(refetch, 30_000);
    return () => clearInterval(timer);
  }, [refetch]);

  useEffect(() => {
    const handler = (_event: WSEvent) => {
      void refetch();
    };
    for (const eventType of INVALIDATION_EVENTS) wsManager.on(eventType, handler);
    return () => {
      for (const eventType of INVALIDATION_EVENTS) wsManager.off(eventType, handler);
    };
  }, [refetch]);

  return { summary, loading, error, refetch };
}
