"use client";

import { useState } from "react";
import { useDecisions } from "@/hooks/useDecisions";
import type { DecisionCard } from "@/lib/api";
import { BrandIcon } from "@/components/ui/brand-icons";

function riskClass(risk?: string | null, variant: "dark" | "light" = "dark") {
  const raw = (risk ?? "").toLowerCase();
  if (variant === "light") {
    if (raw.includes("high")) return "border-red-200 bg-red-50 text-red-700";
    if (raw.includes("med")) return "border-amber-200 bg-amber-50 text-amber-700";
    if (raw.includes("low")) return "border-emerald-200 bg-emerald-50 text-emerald-700";
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  if (raw.includes("high")) return "border-red-500/35 bg-red-500/10 text-red-200";
  if (raw.includes("med")) return "border-amber-500/35 bg-amber-500/10 text-amber-200";
  if (raw.includes("low")) return "border-emerald-500/35 bg-emerald-500/10 text-emerald-200";
  return "border-blue-500/35 bg-blue-500/10 text-blue-200";
}

function labelForType(type: string) {
  const raw = type.toLowerCase();
  if (raw.includes("approve")) return "Approval";
  if (raw.includes("choose")) return "Choice";
  if (raw.includes("unblock")) return "Unblock";
  if (raw.includes("escalate")) return "Escalation";
  return "Clarification";
}

function confidence(card: DecisionCard) {
  if (typeof card.confidence !== "number") return null;
  return `${Math.round(card.confidence * 100)}% confidence`;
}

function formatDeadline(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" }).format(date);
}

export function DecisionNudgePanel({ roomId, compact = false, variant = "dark" }: { roomId?: string; compact?: boolean; variant?: "dark" | "light" }) {
  const { decisions, loading, error, answerDecision, snoozeDecision, delegateDecision } = useDecisions(roomId, "pending");
  const [busyId, setBusyId] = useState<string | null>(null);
  const primary = decisions[0];
  const light = variant === "light";

  const run = async (id: string, action: () => Promise<unknown>) => {
    setBusyId(id);
    try {
      await action();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className={`rounded-xl border ${light ? "border-slate-200 bg-white shadow-[0_10px_34px_rgba(15,23,42,0.06)]" : "border-white/10 bg-[#080a0f]"} ${compact ? "p-4" : "p-5"}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <BrandIcon className={light ? "text-blue-600" : "text-blue-300"} name="inspect" size={18} />
            <h2 className={`text-sm font-semibold ${light ? "text-slate-950" : "text-white"}`}>Decision Inbox</h2>
          </div>
          <p className={`mt-1 text-xs ${light ? "text-slate-500" : "text-zinc-500"}`}>{roomId ?? "all rooms"} · {decisions.length} pending</p>
        </div>
        {decisions.length > 0 && (
          <span className={`rounded-full border px-2.5 py-1 text-xs ${light ? "border-blue-200 bg-blue-50 text-blue-700" : "border-blue-500/30 bg-blue-500/10 text-blue-200"}`}>
            Nudge
          </span>
        )}
      </div>

      {loading && <p className={`mt-4 text-sm ${light ? "text-slate-400" : "text-zinc-500"}`}>Loading decisions...</p>}
      {error && <p className={`mt-4 text-sm ${light ? "text-red-600" : "text-red-300"}`}>{error}</p>}
      {!loading && !error && !primary && (
        <div className={`mt-4 rounded-lg border p-4 ${light ? "border-slate-200 bg-slate-50" : "border-white/10 bg-white/[0.035]"}`}>
          <p className={`text-sm font-medium ${light ? "text-slate-900" : "text-zinc-200"}`}>No pending decisions.</p>
          <p className={`mt-1 text-xs leading-5 ${light ? "text-slate-500" : "text-zinc-500"}`}>Agents can keep working until they need approval, clarification, or escalation.</p>
        </div>
      )}

      {primary && (
        <div className={`mt-4 rounded-xl border p-4 ${light ? "border-blue-200 bg-blue-50 shadow-[0_10px_34px_rgba(37,99,235,0.1)]" : "border-blue-500/30 bg-blue-500/[0.08] shadow-[0_18px_60px_rgba(37,99,235,0.16)]"}`}>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-md border px-2 py-1 text-[11px] ${light ? "border-slate-200 bg-white text-slate-600" : "border-white/10 bg-white/[0.06] text-zinc-300"}`}>{labelForType(primary.decision_type)}</span>
            {primary.risk && <span className={`rounded-md border px-2 py-1 text-[11px] ${riskClass(primary.risk, variant)}`}>{primary.risk}</span>}
            {confidence(primary) && <span className={`rounded-md border px-2 py-1 text-[11px] ${light ? "border-slate-200 bg-white text-slate-500" : "border-white/10 bg-white/[0.05] text-zinc-400"}`}>{confidence(primary)}</span>}
            {formatDeadline(primary.deadline) && <span className={`ml-auto text-[11px] ${light ? "text-slate-500" : "text-zinc-500"}`}>{formatDeadline(primary.deadline)}</span>}
          </div>
          <h3 className={`mt-3 text-base font-semibold leading-6 ${light ? "text-slate-950" : "text-white"}`}>{primary.question}</h3>
          {primary.context && <p className={`mt-2 text-sm leading-5 ${light ? "text-slate-600" : "text-zinc-400"}`}>{primary.context}</p>}
          <div className="mt-4 flex flex-wrap gap-2">
            {(primary.options?.length ? primary.options : ["Approve"]).slice(0, 3).map((option) => (
              <button
                className={`rounded-lg px-3 py-2 text-sm font-medium disabled:opacity-50 ${
                  option === primary.recommended_option
                    ? "bg-accent text-white"
                    : light ? "border border-slate-200 bg-white text-slate-700" : "border border-white/10 bg-white/[0.05] text-zinc-200"
                }`}
                disabled={busyId === primary.decision_id}
                key={option}
                onClick={() => void run(primary.decision_id, () => answerDecision(primary.decision_id, option))}
                type="button"
              >
                {option}
              </button>
            ))}
            <button
              className={`rounded-lg border px-3 py-2 text-sm disabled:opacity-50 ${light ? "border-slate-200 bg-white text-slate-600" : "border-white/10 bg-white/[0.035] text-zinc-300"}`}
              disabled={busyId === primary.decision_id}
              onClick={() => void run(primary.decision_id, () => delegateDecision(primary.decision_id, primary.source_agent_id || "pm-agent", "Delegated from nudge card"))}
              type="button"
            >
              Delegate
            </button>
            <button
              className={`rounded-lg border px-3 py-2 text-sm disabled:opacity-50 ${light ? "border-slate-200 bg-white text-slate-500" : "border-white/10 bg-white/[0.035] text-zinc-400"}`}
              disabled={busyId === primary.decision_id}
              onClick={() => void run(primary.decision_id, () => snoozeDecision(primary.decision_id))}
              type="button"
            >
              Snooze
            </button>
          </div>
          <div className={`mt-4 flex flex-wrap gap-3 text-[11px] ${light ? "text-slate-500" : "text-zinc-500"}`}>
            {primary.source_agent_id && <span>from {primary.source_agent_id}</span>}
            {primary.task_id && <span>task {primary.task_id}</span>}
            {primary.cost_estimate && <span>cost {primary.cost_estimate}</span>}
            <span>BYOK safe</span>
          </div>
        </div>
      )}

      {decisions.length > 1 && (
        <div className="mt-3 space-y-2">
          {decisions.slice(1, compact ? 3 : 6).map((item) => (
            <div className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${light ? "border-slate-200 bg-slate-50" : "border-white/10 bg-white/[0.035]"}`} key={item.decision_id}>
              <span className={`size-2 rounded-full ${item.risk?.toLowerCase().includes("high") ? "bg-red-400" : "bg-blue-400"}`} />
              <span className={`min-w-0 flex-1 truncate text-sm ${light ? "text-slate-700" : "text-zinc-300"}`}>{item.question}</span>
              <button
                className={`rounded border px-2 py-1 text-xs ${light ? "border-slate-200 bg-white text-slate-600" : "border-white/10 text-zinc-300"}`}
                disabled={busyId === item.decision_id}
                onClick={() => void run(item.decision_id, () => answerDecision(item.decision_id, item.recommended_option || item.options?.[0] || "Approved"))}
                type="button"
              >
                Resolve
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
