"use client";

import { useEffect, useRef } from "react";
import { useAgentActivity, type ActivityItem } from "@/hooks/useAgentActivity";
import { useAgentPanel } from "@/contexts/AgentPanelContext";

// ── Compact activity line renderer ──────────────────────────────

function ActivityLine({ item }: { item: ActivityItem }) {
  const m = item.metadata;

  switch (item.kind) {
    case "started":
      return (
        <div className="flex gap-2 text-indigo-400">
          <span className="text-zinc-600 shrink-0">{item.timestamp}</span>
          <span>
            ▶ <span className="text-zinc-300">{m.subject as string}</span>
            {m.complexity ? (
              <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                {String(m.complexity)}
              </span>
            ) : null}
            {m.model ? (
              <span className="ml-1 text-[10px] text-zinc-600">{String(m.model)}</span>
            ) : null}
          </span>
        </div>
      );

    case "tool_use":
      return (
        <div className="flex gap-2 text-zinc-500">
          <span className="text-zinc-700 shrink-0">{item.timestamp}</span>
          <span>
            <span className="text-amber-500/80">⚡</span>{" "}
            <span className="text-cyan-400/70">{m.tool_name as string}</span>{" "}
            <span className="text-zinc-600 truncate inline-block max-w-[280px] align-bottom">
              {m.tool_args as string}
            </span>
          </span>
        </div>
      );

    case "progress": {
      const elapsed = Number(m.elapsed_sec) || 0;
      const count = Number(m.changed_count) || 0;
      const files = (m.files_changed as string[]) || [];
      return (
        <div className="flex gap-2 text-zinc-500">
          <span className="text-zinc-700 shrink-0">{item.timestamp}</span>
          <span>
            ⏳ {elapsed}s
            {count > 0 ? <span className="text-zinc-400"> · {count} files</span> : null}
            {files.length > 0 ? (
              <span className="text-zinc-600 text-[10px] ml-2">
                {files.slice(0, 3).join(", ")}
                {files.length > 3 ? ` +${files.length - 3}` : null}
              </span>
            ) : null}
          </span>
        </div>
      );
    }

    case "completed":
      return (
        <div className="flex gap-2 text-emerald-400">
          <span className="text-zinc-600 shrink-0">{item.timestamp}</span>
          <span>
            ✓ completed
            {m.changed_count ? (
              <span className="text-zinc-400 ml-1">· {String(m.changed_count)} files</span>
            ) : null}
            {m.pr_url ? (
              <a
                href={m.pr_url as string}
                target="_blank"
                rel="noreferrer"
                className="ml-2 text-cyan-400 underline text-[11px]"
              >
                PR
              </a>
            ) : null}
          </span>
        </div>
      );

    case "error":
      return (
        <div className="flex gap-2 text-red-400">
          <span className="text-zinc-600 shrink-0">{item.timestamp}</span>
          <span>✗ {item.text || "error"}</span>
        </div>
      );

    default:
      return (
        <div className="flex gap-2 text-zinc-600">
          <span className="text-zinc-700 shrink-0">{item.timestamp}</span>
          <span>{item.text}</span>
        </div>
      );
  }
}

// ── Main Panel ──────────────────────────────────────────────────

export function AgentActivityPanel() {
  const { selectedAgentId, selectedAgentLabel, closeAgentPanel } = useAgentPanel();
  const { activities, loading, currentTask } = useAgentActivity(
    selectedAgentLabel || undefined,
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activities.length]);

  if (!selectedAgentId) return null;

  const taskMeta = currentTask?.metadata;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-40"
        onClick={closeAgentPanel}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-[420px] bg-zinc-950 border-l border-zinc-800 z-50 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-900/80">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-zinc-200 font-mono text-sm font-semibold">
              {selectedAgentLabel || selectedAgentId}
            </span>
          </div>
          <button
            onClick={closeAgentPanel}
            className="text-zinc-500 hover:text-zinc-300 text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* Current task info */}
        {taskMeta && (
          <div className="px-4 py-2 border-b border-zinc-800/50 bg-zinc-900/40 font-mono text-[11px] space-y-0.5">
            <div className="text-zinc-400">
              <span className="text-zinc-600">task</span>{" "}
              <span className="text-indigo-400">{String(taskMeta.task_id || "").slice(0, 14)}</span>
            </div>
            <div className="text-zinc-300 truncate">{String(taskMeta.subject || "")}</div>
            <div className="flex gap-3 text-zinc-600">
              {taskMeta.complexity ? <span>{String(taskMeta.complexity)}</span> : null}
              {taskMeta.model ? <span>{String(taskMeta.model)}</span> : null}
            </div>
          </div>
        )}

        {/* Activity feed */}
        <div className="flex-1 overflow-y-auto px-4 py-3 font-mono text-[11px] leading-relaxed space-y-1">
          {loading && (
            <div className="text-zinc-600 animate-pulse">loading history...</div>
          )}
          {!loading && activities.length === 0 && (
            <div className="text-zinc-700">no activity yet</div>
          )}
          {activities.map((item) => (
            <ActivityLine key={item.id} item={item} />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-zinc-800 text-[10px] text-zinc-700 font-mono">
          {activities.length} events · live
        </div>
      </div>
    </>
  );
}
