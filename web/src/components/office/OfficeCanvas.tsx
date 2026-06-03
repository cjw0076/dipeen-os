"use client";

import { useRef } from "react";
import { useOfficeEngine } from "./useOfficeEngine";
import { useTasks } from "@/hooks/useTasks";
import { useUsage } from "@/hooks/useUsage";
import { EventBus } from "@/game/EventBus";
import { api } from "@/lib/api";
import { AgentCardPanel } from "./AgentCardPanel";
import { MeetingPanel } from "./MeetingPanel";
import { getUserName } from "@/hooks/useUserProfile";

export function OfficeCanvas() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const {
    loaded,
    agents,
    selectedAgent,
    lastMessages,
    meetingZoneAgentIds,
  } = useOfficeEngine(canvasRef);
  const meetingAgents = agents.filter(a => meetingZoneAgentIds.includes(a.id));
  const { tasks } = useTasks();
  const { usage } = useUsage();

  // Per-agent stats derived from live data
  const agentTokens = selectedAgent
    ? (usage.by_agent?.[selectedAgent.id] ?? 0)
    : 0;
  const agentTasks = selectedAgent
    ? tasks.filter((t) => t.assigned_agent_id === (selectedAgent.dbId ?? null))
    : [];
  const tasksDone = agentTasks.filter((t) => t.status === "done").length;
  const tasksPct = agentTasks.length > 0
    ? Math.round((tasksDone / agentTasks.length) * 100)
    : 0;


  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-border-subtle shrink-0">
        <div>
          <span className="text-sm font-medium">Virtual Office</span>
          <span className="ml-2 text-[11px] text-text-muted">
            {agents.filter(a => a.status !== "offline").length} online
          </span>
        </div>
        <div className="flex gap-3 text-[11px] text-text-muted">
          {meetingZoneAgentIds.length > 0 && (
            <span className="flex items-center gap-1 text-[#a78bfa]">
              Meeting: {meetingZoneAgentIds.length}
            </span>
          )}
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#60A5FA]" /> Working
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#52525B]" /> Idle
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-zinc-700" /> Offline
          </span>
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 relative overflow-hidden" style={{ background: "#1E1E2E" }}>
        {!loaded && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="text-text-muted text-sm animate-pulse">Loading office...</div>
          </div>
        )}
        <div
          ref={canvasRef}
          style={{ width: "100%", height: "100%" }}
        />

        {/* Hint */}
        {!selectedAgent && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 text-[11px] text-text-muted/50 font-mono">
            Right-click to move · Click agent to inspect
          </div>
        )}

        <MeetingPanel
          agents={meetingAgents}
          onRequestMeeting={() => {
            api.chat.send("🏢 회의 시작 요청합니다.", "general", getUserName?.() ?? "사용자").catch(() => {});
          }}
          onClose={() => {/* auto-closes when agents leave zone */}}
        />

        <AgentCardPanel
          agent={selectedAgent}
          tokens={agentTokens}
          lastMessage={selectedAgent ? (lastMessages[selectedAgent.role] ?? null) : null}
          onChat={() => {
            EventBus.emit("focus-chat-room", {});
          }}
          onCancel={async () => {
            if (selectedAgent?.taskId) {
              try { await api.tasks.cancel(selectedAgent.taskId); } catch { /* ignore */ }
            }
          }}
          onClose={() => EventBus.emit("agent-selected", null)}
          onSendMessage={(text) => {
            api.chat.send(
              `@${selectedAgent?.label ?? "에이전트"} ${text}`,
              "general",
              getUserName?.() ?? "사용자"
            ).catch(() => {});
          }}
        />
      </div>
    </div>
  );
}
