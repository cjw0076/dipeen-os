"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type DecisionCard } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export function useDecisions(roomId?: string, status = "pending") {
  const [decisions, setDecisions] = useState<DecisionCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.decisions.list({ roomId, status, limit: 50 });
      setDecisions(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [roomId, status]);

  useEffect(() => {
    refetch();
    const timer = setInterval(refetch, 30_000);
    return () => clearInterval(timer);
  }, [refetch]);

  useEffect(() => {
    const handler = (event: WSEvent) => {
      const eventRoomId = event.room_id as string | undefined;
      if (!roomId || !eventRoomId || eventRoomId === roomId) {
        refetch();
      }
    };
    wsManager.on("decision_created", handler);
    wsManager.on("decision_updated", handler);
    return () => {
      wsManager.off("decision_created", handler);
      wsManager.off("decision_updated", handler);
    };
  }, [refetch, roomId]);

  const answerDecision = useCallback(async (decisionId: string, answer: string, note?: string) => {
    const updated = await api.decisions.answer(decisionId, answer, note);
    setDecisions((prev) => prev.filter((item) => item.decision_id !== updated.decision_id));
    return updated;
  }, []);

  const snoozeDecision = useCallback(async (decisionId: string) => {
    const updated = await api.decisions.snooze(decisionId);
    setDecisions((prev) => prev.filter((item) => item.decision_id !== updated.decision_id));
    return updated;
  }, []);

  const delegateDecision = useCallback(async (decisionId: string, delegateTo: string, note?: string) => {
    const updated = await api.decisions.delegate(decisionId, delegateTo, note);
    setDecisions((prev) => prev.filter((item) => item.decision_id !== updated.decision_id));
    return updated;
  }, []);

  return {
    decisions,
    loading,
    error,
    pendingCount: decisions.length,
    refetch,
    answerDecision,
    snoozeDecision,
    delegateDecision,
  };
}
