"use client";

import { useEffect, useMemo, useState } from "react";
import { useArtifactContent } from "@/hooks/useArtifactContent";
import type { ControlPlaneArtifact } from "@/lib/api";

type TabKey = "diff" | "stdout" | "tests";

function filenameForType(type: string): string | undefined {
  if (type === "code_patch") return "diff.patch";
  if (type === "command_receipt") return "stdout.txt";
  if (type === "test_report") return "test_output.txt";
  return undefined;
}

function tabForType(type: string): TabKey {
  if (type === "code_patch") return "diff";
  if (type === "test_report") return "tests";
  return "stdout";
}

function DiffView({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <pre className="overflow-auto rounded-lg bg-slate-950 p-3 text-[12px] leading-5">
      {lines.map((line, i) => {
        const tone = line.startsWith("+") && !line.startsWith("+++") ? "text-emerald-300 bg-emerald-950/40"
          : line.startsWith("-") && !line.startsWith("---") ? "text-red-300 bg-red-950/40"
          : line.startsWith("@@") ? "text-sky-300" : "text-slate-300";
        return <div className={`whitespace-pre ${tone}`} key={i}>{line || " "}</div>;
      })}
    </pre>
  );
}

export function EvidenceDetailModal({
  artifact,
  onClose,
}: {
  artifact: ControlPlaneArtifact | null;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<TabKey>("stdout");
  const filename = artifact ? filenameForType(artifact.type) : undefined;
  const { content, loading, error } = useArtifactContent(artifact?.artifact_id ?? null, filename);

  useEffect(() => {
    if (artifact) setTab(tabForType(artifact.type));
  }, [artifact]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const failures = useMemo(
    () => (artifact?.evidence ?? []).filter((e) => e.kind === "test_failed"),
    [artifact],
  );

  if (!artifact) return null;
  const tabs: TabKey[] = artifact.type === "test_report" ? ["tests", "stdout"]
    : artifact.type === "code_patch" ? ["diff"] : ["stdout"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4" onClick={onClose}>
      <div
        className="flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[var(--ds-border)] bg-white shadow-[var(--ds-shadow-floating)]"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-[var(--ds-border)] px-5 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-bold text-[var(--ds-text)]">{artifact.title || artifact.type}</h2>
            <p className="mt-0.5 text-xs text-[var(--ds-text-muted)]">{artifact.summary}</p>
          </div>
          <button className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-700" onClick={onClose} type="button">Close (Esc)</button>
        </header>

        <div className="flex gap-1 border-b border-[var(--ds-border)] px-5 pt-2">
          {tabs.map((t) => (
            <button
              className={`rounded-t-lg px-3 py-2 text-xs font-bold ${tab === t ? "border-b-2 border-[var(--ds-primary)] text-[var(--ds-primary)]" : "text-slate-500"}`}
              key={t}
              onClick={() => setTab(t)}
              type="button"
            >
              {t === "diff" ? "Diff" : t === "stdout" ? "Stdout" : "Tests"}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-5">
          {content?.truncated && (
            <p className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-800">본문이 사이즈 캡으로 잘렸습니다 (truncated).</p>
          )}
          {loading && <p className="text-sm text-slate-500">Loading evidence body…</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {!loading && !error && tab === "tests" && (
            <div className="space-y-2">
              <p className="text-sm font-bold text-slate-800">{artifact.summary}</p>
              {failures.length === 0 && <p className="text-sm text-emerald-700">No failing cases.</p>}
              {failures.map((f, i) => (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" key={i}>{f.message}</div>
              ))}
              {content?.available && <pre className="mt-3 overflow-auto rounded-lg bg-slate-50 p-3 text-[12px] leading-5 text-slate-700">{content.content}</pre>}
            </div>
          )}
          {!loading && !error && tab === "diff" && (content?.available ? <DiffView text={content.content} /> : <p className="text-sm text-slate-500">No diff body persisted for this artifact.</p>)}
          {!loading && !error && tab === "stdout" && (content?.available ? <pre className="overflow-auto rounded-lg bg-slate-50 p-3 text-[12px] leading-5 text-slate-700">{content.content}</pre> : <p className="text-sm text-slate-500">No stdout body persisted.</p>)}
        </div>
      </div>
    </div>
  );
}
