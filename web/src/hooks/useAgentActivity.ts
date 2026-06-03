"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export interface ActivityItem {
  id: string;
  kind: string;            // started | progress | tool_use | completed | error
  timestamp: string;
  task_id?: string;
  metadata: Record<string, unknown>;
  text: string;
}

/**
 * Real-time agent activity feed.
 * Fetches history + subscribes to live WS events.
 * @param agentLabel - Agent display name (e.g. "FE Agent")
 * @param taskId - Optional: filter by task_id only
 * @param roomId - Project/meeting room to read activity from
 */
export function useAgentActivity(agentLabel?: string, taskId?: string, roomId = "general") {
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const seenIds = useRef(new Set<string>());

  // Load history on mount
  useEffect(() => {
    if (!agentLabel && !taskId) {
      setLoading(false);
      return;
    }

    setActivities([]);
    seenIds.current.clear();
    setLoading(true);

    api.chat
      .history(roomId, 200, {
        sender: agentLabel || undefined,
        taskId: taskId || undefined,
      })
      .then((hist) => {
        const items: ActivityItem[] = [];
        for (const m of hist) {
          if (!m.metadata_json) continue;
          const kind = (m.metadata_json.kind as string) || "unknown";
          seenIds.current.add(m.id);
          items.push({
            id: m.id,
            kind,
            timestamp: m.timestamp,
            task_id: m.task_id,
            metadata: m.metadata_json,
            text: m.text,
          });
        }
        setActivities(items);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [agentLabel, taskId, roomId]);

  // Live WS subscription
  useEffect(() => {
    if (!agentLabel && !taskId) return;

    const handler = (e: WSEvent) => {
      const ev = e as unknown as Record<string, unknown>;
      const meta = ev.metadata_json as Record<string, unknown> | undefined;
      if (!meta) return;

      // Filter by agent or task
      if (roomId && ev.room_id && ev.room_id !== roomId) return;
      if (agentLabel && ev.sender !== agentLabel) return;
      if (taskId && ev.task_id !== taskId) return;

      const id = (ev.id as string) || `ws-${Date.now()}`;
      if (seenIds.current.has(id)) return;
      seenIds.current.add(id);

      const item: ActivityItem = {
        id,
        kind: (meta.kind as string) || "unknown",
        timestamp:
          (ev.timestamp as string) ||
          new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }),
        task_id: (ev.task_id as string) || undefined,
        metadata: meta,
        text: (ev.text as string) || "",
      };
      setActivities((prev) => [...prev, item]);
    };

    wsManager.on("chat_message", handler);
    return () => wsManager.off("chat_message", handler);
  }, [agentLabel, taskId, roomId]);

  // Derive current task from latest "started" event
  const currentTask = activities
    .filter((a) => a.kind === "started")
    .at(-1);

  return { activities, loading, currentTask };
}
