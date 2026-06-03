"use client";

import { useState, useEffect, useCallback } from "react";
import { api, type Agent } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export const ROLE_COLOR: Record<string, string> = {
  PM: "#FBBF24",
  FE: "#60A5FA",
  BE: "#34D399",
  QA: "#A78BFA",
};

export const ROLE_NUMERIC: Record<string, number> = {
  PM: 0,
  FE: 1,
  BE: 2,
  QA: 3,
};

export interface LiveAgent extends Agent {
  color: string;
  label: string;
}

function enrich(a: Agent): LiveAgent {
  const role = a.role?.toUpperCase() ?? "";
  return {
    ...a,
    color: ROLE_COLOR[role] ?? "#888888",
    label: a.agent_id
      .split(/[-_]/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" "),
  };
}

export function useAgents() {
  const [agents, setAgents] = useState<LiveAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const data = await api.agents.list();
      setAgents(data.map(enrich));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch + 30s polling fallback
  useEffect(() => {
    fetchAgents();
    const timer = setInterval(fetchAgents, 30_000);
    return () => clearInterval(timer);
  }, [fetchAgents]);

  // Real-time WS updates
  useEffect(() => {
    const handler = (e: WSEvent) => {
      const ev = e as unknown as {
        agent_id: string;
        status: string;
        current_task_id: string | null;
        competency?: Record<string, number>;
        skills?: string[];
      };
      setAgents((prev) =>
        prev.map((a) => {
          if (a.agent_id !== ev.agent_id) return a;
          const updatedMeta = ev.competency || ev.skills
            ? {
                ...(a.metadata_json as Record<string, unknown> || {}),
                ...(ev.competency ? { competency: ev.competency } : {}),
                ...(ev.skills ? { skills: ev.skills } : {}),
              }
            : a.metadata_json;
          return {
            ...a,
            status: ev.status,
            current_task_id: ev.current_task_id ?? null,
            metadata_json: updatedMeta,
          };
        })
      );
    };
    wsManager.on("agent_status", handler);
    return () => wsManager.off("agent_status", handler);
  }, []);

  return { agents, loading, error, refetch: fetchAgents };
}
