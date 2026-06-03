"use client";

import type { Participant } from "@/hooks/useMeeting";

function TypingDots() {
  return (
    <span className="inline-flex gap-0.5 items-center ml-1">
      <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-1 h-1 rounded-full bg-current animate-bounce" style={{ animationDelay: "300ms" }} />
    </span>
  );
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    working: "bg-status-working",
    idle: "bg-status-idle",
    done: "bg-status-done",
    error: "bg-status-error",
    offline: "bg-zinc-700",
  };
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      {status === "working" && (
        <span className="absolute inline-flex h-full w-full rounded-full bg-status-working opacity-75 animate-ping" />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${colors[status] ?? "bg-zinc-700"}`} />
    </span>
  );
}

interface Props {
  participants: Participant[];
}

export function ParticipantPanel({ participants }: Props) {
  const list = participants;

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest mb-1">
        Participants
      </p>

      {/* Human user */}
      <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-md bg-bg-elevated/50">
        <div className="w-7 h-7 rounded-full bg-bg-elevated border border-border-subtle flex items-center justify-center text-[11px] font-medium text-text-secondary shrink-0">
          You
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] text-text-primary">You</p>
          <p className="text-[11px] text-text-muted">사용자</p>
        </div>
        <StatusDot status="idle" />
      </div>

      {/* Agents */}
      {list.map((p) => (
        <div
          key={p.agent_id}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-md hover:bg-bg-hover/30 transition-colors"
        >
          <div
            className="w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-bold text-black/80 shrink-0"
            style={{ backgroundColor: p.color }}
          >
            {p.role}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] text-text-primary flex items-center gap-1">
              {p.agent_id}
              {p.typing && (
                <span style={{ color: p.color }}>
                  <TypingDots />
                </span>
              )}
            </p>
            <p className="text-[11px] text-text-muted">{p.role} Agent</p>
          </div>
          <StatusDot status={p.typing ? "working" : p.status} />
        </div>
      ))}
    </div>
  );
}
