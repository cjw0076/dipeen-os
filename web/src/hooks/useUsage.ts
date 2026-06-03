"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export interface UsageSummary {
  total_tokens: number;
  today_tokens: number;
  by_agent: Record<string, number>;
}

export function useUsage() {
  const [usage, setUsage] = useState<UsageSummary>({
    total_tokens: 0,
    today_tokens: 0,
    by_agent: {},
  });

  const fetchUsage = useCallback(async () => {
    try {
      const data = await api.usage.summary();
      setUsage({
        total_tokens: data.total_tokens,
        today_tokens: data.today_tokens,
        by_agent: data.by_agent,
      });
    } catch {
      // non-critical: keep existing values
    }
  }, []);

  // Initial fetch + 60s polling fallback
  useEffect(() => {
    fetchUsage();
    const timer = setInterval(fetchUsage, 60_000);
    return () => clearInterval(timer);
  }, [fetchUsage]);

  // Real-time WS updates
  useEffect(() => {
    const handler = (e: WSEvent) => {
      const ev = e as unknown as { agent_id: string; token_count: number };
      setUsage((prev) => ({
        total_tokens: prev.total_tokens + ev.token_count,
        today_tokens: prev.today_tokens + ev.token_count,
        by_agent: {
          ...prev.by_agent,
          [ev.agent_id]: (prev.by_agent[ev.agent_id] ?? 0) + ev.token_count,
        },
      }));
    };
    wsManager.on("usage_update", handler);
    return () => wsManager.off("usage_update", handler);
  }, []);

  return { usage, refetch: fetchUsage };
}
