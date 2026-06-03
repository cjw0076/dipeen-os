"use client";

import { useState } from "react";

type Metadata = {
  kind: string;
  task_id?: string;
  elapsed_sec?: number;
  files_changed?: string[];
  changed_count?: number;
  model?: string;
  tool_name?: string;
  tool_args?: string;
  subject?: string;
  complexity?: string;
  pr_url?: string;
  error?: string;
};

function FileList({ files }: { files: string[] }) {
  const [expanded, setExpanded] = useState(false);
  if (files.length === 0) return null;

  const shown = expanded ? files : files.slice(0, 3);
  const more = files.length - 3;

  return (
    <div className="mt-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-[10px] text-accent hover:underline"
      >
        {expanded ? "Hide files" : `${files.length} files changed`}
      </button>
      {(expanded || files.length <= 3) && (
        <div className="mt-0.5 space-y-0.5">
          {shown.map((f) => (
            <div key={f} className="text-[10px] text-text-muted font-mono truncate pl-2 border-l border-border-subtle">
              {f}
            </div>
          ))}
          {!expanded && more > 0 && (
            <div className="text-[10px] text-text-muted pl-2">+{more} more</div>
          )}
        </div>
      )}
    </div>
  );
}

export function ActivityCard({ meta, color }: { meta: Metadata; color: string }) {
  switch (meta.kind) {
    case "started":
      return (
        <div className="flex items-center gap-2 py-1 px-2 rounded-md bg-indigo-500/10 border border-indigo-500/20">
          <span className="text-[18px]">▶</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-semibold" style={{ color }}>
                {meta.subject}
              </span>
              {meta.complexity && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted uppercase">
                  {meta.complexity}
                </span>
              )}
            </div>
            <div className="text-[10px] text-text-muted mt-0.5">
              {meta.task_id?.slice(0, 12)} {meta.model && `· ${meta.model}`}
            </div>
          </div>
        </div>
      );

    case "progress":
      return (
        <div className="py-1 px-2 rounded-md bg-bg-elevated/50 border border-border/30">
          <div className="flex items-center gap-2">
            <span className="text-[14px] animate-pulse">⏳</span>
            <span className="text-[11px] text-text-secondary">
              {meta.elapsed_sec}s · {meta.changed_count ?? 0} files
            </span>
            {meta.model && (
              <span className="text-[9px] text-text-muted font-mono ml-auto">{meta.model}</span>
            )}
          </div>
          {meta.files_changed && meta.files_changed.length > 0 && (
            <FileList files={meta.files_changed} />
          )}
        </div>
      );

    case "tool_use":
      return (
        <div className="flex items-center gap-1.5 py-0.5 text-[10px] text-text-muted">
          <span>🔧</span>
          <span className="font-mono text-indigo-400">{meta.tool_name}</span>
          <span className="truncate max-w-[300px]">{meta.tool_args}</span>
        </div>
      );

    case "completed":
      return (
        <div className="flex items-center gap-2 py-1 px-2 rounded-md bg-green-500/10 border border-green-500/20">
          <span className="text-[18px]">✅</span>
          <div className="flex-1 min-w-0">
            <span className="text-[12px] font-semibold text-green-400">
              {meta.subject || "Task completed"}
            </span>
            <div className="text-[10px] text-text-muted mt-0.5">
              {meta.changed_count && `${meta.changed_count} files changed`}
              {meta.pr_url && (
                <a href={meta.pr_url} target="_blank" rel="noopener noreferrer"
                  className="ml-2 text-indigo-400 hover:underline">
                  PR →
                </a>
              )}
            </div>
          </div>
        </div>
      );

    case "error":
      return (
        <div className="flex items-center gap-2 py-1 px-2 rounded-md bg-red-500/10 border border-red-500/20">
          <span className="text-[18px]">❌</span>
          <div className="flex-1 min-w-0">
            <span className="text-[12px] font-semibold text-red-400">
              {meta.subject || "Task failed"}
            </span>
            {meta.error && (
              <div className="text-[10px] text-red-300/70 mt-0.5">{meta.error}</div>
            )}
          </div>
        </div>
      );

    default:
      return null;
  }
}
