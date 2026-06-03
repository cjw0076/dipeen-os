"use client";

import { useState, useEffect } from "react";
import type { LiveAgent } from "@/hooks/useAgents";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 5)   return "just now";
  if (diff < 60)  return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

const STATUS_DOT: Record<string, string> = {
  working: "#22C55E",
  idle:    "#60A5FA",
  offline: "#52525B",
};

const STATUS_LABEL: Record<string, string> = {
  working: "Working",
  idle:    "Idle",
  offline: "Offline",
};

// ─── AgentStatusCard ──────────────────────────────────────────────────────────

interface Props {
  agent: LiveAgent;
  tasksDone: number;
  tasksTotal: number;
}

export function AgentStatusCard({ agent, tasksDone, tasksTotal }: Props) {
  // Re-render every 10 s to keep relative-time fresh
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 10_000);
    return () => clearInterval(id);
  }, []);

  const role = (agent.role ?? "").toUpperCase();
  const dotColor = STATUS_DOT[agent.status] ?? STATUS_DOT.offline;
  const statusLabel = STATUS_LABEL[agent.status] ?? agent.status;

  const competency =
    (agent.metadata_json?.competency as Record<string, number> | undefined) ?? {};
  const score = competency[role] ?? 0;
  const pct =
    score > 0
      ? Math.min(100, Math.round(score))
      : tasksTotal > 0
      ? Math.round((tasksDone / tasksTotal) * 100)
      : 0;
  const perfLabel =
    score > 0 ? `${score}/100` : `${tasksDone}/${tasksTotal} tasks`;

  const hbTime = relativeTime(agent.last_heartbeat);
  const isOnline = agent.status !== "offline";

  return (
    <div
      className={`rounded-lg border p-3 space-y-2.5 transition-colors ${
        isOnline ? "border-border/60 bg-bg-elevated" : "border-border/30 bg-bg-elevated/40 opacity-60"
      }`}
    >
      {/* Top row: avatar + name + status */}
      <div className="flex items-center gap-2.5">
        {/* Role badge with status dot */}
        <div className="relative shrink-0">
          <div
            className="w-8 h-8 rounded-md text-[11px] font-bold flex items-center justify-center text-black/80"
            style={{ backgroundColor: agent.color }}
          >
            {role || "?"}
          </div>
          <span
            className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-bg-card"
            style={{ backgroundColor: dotColor }}
            title={statusLabel}
          />
        </div>

        {/* Name + status */}
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-medium text-text-secondary truncate leading-tight">
            {agent.label}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-[10px]" style={{ color: dotColor }}>
              {statusLabel}
            </span>
            <span className="text-[10px] text-text-muted">·</span>
            <span className="text-[10px] text-text-muted font-mono">{hbTime}</span>
          </div>
        </div>
      </div>

      {/* Current task (only when working) */}
      {agent.status === "working" && agent.current_task_id && (
        <div className="flex items-center gap-1.5 bg-green-950/30 rounded px-2 py-1 border border-green-900/30">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse shrink-0" />
          <span className="text-[10px] font-mono text-green-400 truncate">
            {agent.current_task_id}
          </span>
        </div>
      )}

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <span className="text-[10px] text-text-muted">Performance</span>
          <span className="text-[10px] text-text-muted font-mono">{perfLabel}</span>
        </div>
        <div className="h-1 bg-bg-card rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${pct}%`, backgroundColor: agent.color }}
          />
        </div>
      </div>
    </div>
  );
}
