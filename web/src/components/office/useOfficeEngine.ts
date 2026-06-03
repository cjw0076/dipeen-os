"use client";

import { useEffect, useLayoutEffect, useRef, useState, useCallback, useMemo } from "react";
import { EventBus } from "@/game/EventBus";
import { useAgents, ROLE_COLOR, ROLE_NUMERIC } from "@/hooks/useAgents";
import type { LiveAgent } from "@/hooks/useAgents";

// ── Agent types (re-exported so GameScene can import) ────────────

type AgentStatus = "offline" | "idle" | "working" | "reviewing" | "error" | "done";

export interface DipeenAgent {
  id: string;       // agent_id string ("fe-agent") — matches usage.by_agent keys
  dbId?: string;    // DB UUID — matches task.assigned_agent_id
  numericId: number;
  label: string;
  role: string;
  status: AgentStatus;
  color: string;
  task?: string;    // task description/ID for display
  taskId?: string;  // DB task UUID for cancel API
}

// ── Constants ───────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  PM: "PM Agent",
  FE: "FE Agent",
  BE: "BE Agent",
  QA: "QA Agent",
};

function mapApiStatus(s: string): AgentStatus {
  if (s === "working") return "working";
  if (s === "idle") return "idle";
  if (s === "offline") return "offline";
  return "idle";
}

function liveToAgent(a: LiveAgent): DipeenAgent {
  const role = a.role?.toUpperCase() ?? "";
  return {
    id: a.agent_id,
    dbId: a.id,
    numericId: ROLE_NUMERIC[role] ?? 0,
    label: ROLE_LABEL[role] ?? a.label,
    role,
    status: mapApiStatus(a.status),
    color: ROLE_COLOR[role] ?? "#888888",
    task: a.current_task_id ?? undefined,
    taskId: a.current_task_id ?? undefined,
  };
}

// ── Hook ────────────────────────────────────────────────────────

export function useOfficeEngine(containerRef: React.RefObject<HTMLDivElement | null>) {
  const gameRef = useRef<import("phaser").Game | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<DipeenAgent | null>(null);
  const [lastMessages, setLastMessages] = useState<Record<string, string>>({});
  const [meetingZoneAgentIds, setMeetingZoneAgentIds] = useState<string[]>([]);

  const { agents: liveAgents } = useAgents();

  const agents = useMemo((): DipeenAgent[] => liveAgents.map(liveToAgent), [liveAgents]);

  // Initialize Phaser game once
  useLayoutEffect(() => {
    if (gameRef.current || !containerRef.current) return;

    let onSceneReady: (() => void) | null = null;
    let onAgentSelected: ((id: string | null) => void) | null = null;
    let onAgentLastMessage: ((data: { agentId: string; message: string }) => void) | null = null;
    let onMeetingZone: ((ids: string[]) => void) | null = null;

    // Dynamically import to avoid SSR issues with Phaser
    import("@/game/main").then(({ createGame }) => {
      if (gameRef.current) return;
      // Use the container div's id or assign one
      const el = containerRef.current;
      if (!el) return;
      if (!el.id) el.id = "office-phaser-container";

      gameRef.current = createGame(el.id);

      onSceneReady = () => setLoaded(true);
      EventBus.on("scene-ready", onSceneReady);

      onAgentSelected = (id: string | null) => {
        if (id === null) {
          setSelectedAgent(null);
        } else {
          setSelectedAgent(agents.find((a) => a.id === id) ?? null);
        }
      };
      EventBus.on("agent-selected", onAgentSelected);

      onAgentLastMessage = (data) => {
        setLastMessages(prev => ({ ...prev, [data.agentId]: data.message }));
      };
      EventBus.on("agent-last-message", onAgentLastMessage);

      onMeetingZone = (ids: string[]) => setMeetingZoneAgentIds(ids);
      EventBus.on("meeting-zone-agents", onMeetingZone);
    });

    return () => {
      if (gameRef.current) {
        gameRef.current.destroy(true);
        gameRef.current = null;
      }
      if (onSceneReady) EventBus.off("scene-ready", onSceneReady);
      if (onAgentSelected) EventBus.off("agent-selected", onAgentSelected);
      if (onAgentLastMessage) EventBus.off("agent-last-message", onAgentLastMessage);
      if (onMeetingZone) EventBus.off("meeting-zone-agents", onMeetingZone);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push agent state changes into Phaser via EventBus
  useEffect(() => {
    if (!loaded) return;
    EventBus.emit("agent-state-update", agents);
  }, [agents, loaded]);

  // Update selectedAgent when agents list refreshes (status change)
  useEffect(() => {
    if (!selectedAgent) return;
    const refreshed = agents.find((a) => a.id === selectedAgent.id);
    if (refreshed) setSelectedAgent(refreshed);
  }, [agents]); // eslint-disable-line react-hooks/exhaustive-deps

  // Phaser handles input internally — these are no-ops for OfficeCanvas JSX compatibility
  const noop = useCallback(() => {}, []);

  return {
    loaded,
    agents,
    selectedAgent,
    lastMessages,
    meetingZoneAgentIds,
    handleClick: noop,
    handleContextMenu: noop,
    handleMouseMove: noop,
    handleMouseLeave: noop,
    handleWheel: noop,
  };
}
