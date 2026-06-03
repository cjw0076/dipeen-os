"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type MemoryCandidate } from "@/lib/api";
import { wsManager } from "@/lib/ws";

export function useMemoryCandidates(status = "pending") {
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.memoryCandidates.list(status);
      setCandidates(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    refetch();
    const timer = setInterval(refetch, 30_000);
    return () => clearInterval(timer);
  }, [refetch]);

  useEffect(() => {
    const handler = () => void refetch();
    wsManager.on("memory.candidate_created", handler);
    wsManager.on("memory.candidate_updated", handler);
    return () => {
      wsManager.off("memory.candidate_created", handler);
      wsManager.off("memory.candidate_updated", handler);
    };
  }, [refetch]);

  const promoteCandidate = useCallback(async (memoryCandidateId: string) => {
    const updated = await api.memoryCandidates.promote(memoryCandidateId);
    setCandidates((prev) => prev.filter((item) => item.memory_candidate_id !== updated.memory_candidate_id));
    return updated;
  }, []);

  const rejectCandidate = useCallback(async (memoryCandidateId: string) => {
    const updated = await api.memoryCandidates.reject(memoryCandidateId);
    setCandidates((prev) => prev.filter((item) => item.memory_candidate_id !== updated.memory_candidate_id));
    return updated;
  }, []);

  return { candidates, loading, error, refetch, promoteCandidate, rejectCandidate };
}
