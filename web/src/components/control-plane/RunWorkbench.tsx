"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { dipeenNavItems, resolveDipeenNavHref } from "@/components/layout/dipeen-nav";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import { useArtifacts } from "@/hooks/useArtifacts";
import { useControlPlaneSummary } from "@/hooks/useControlPlaneSummary";
import { useEvents } from "@/hooks/useEvents";
import { useMemoryCandidates } from "@/hooks/useMemoryCandidates";
import { usePermissions } from "@/hooks/usePermissions";
import { useRuns } from "@/hooks/useRuns";
import { useStateClaims } from "@/hooks/useStateClaims";
import { useTasks } from "@/hooks/useTasks";
import type { ControlPlaneArtifact, ControlPlaneEvent, ControlPlaneRun, StateClaim, Task } from "@/lib/api";

const navItems = dipeenNavItems;

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function shortId(value?: string | null, size = 10) {
  if (!value) return "-";
  return value.length > size ? value.slice(0, size) : value;
}

function statusTone(value?: string | null) {
  const raw = (value ?? "").toLowerCase();
  if (raw.includes("done") || raw.includes("complete") || raw.includes("verified") || raw.includes("passed") || raw.includes("promoted")) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (raw.includes("run") || raw.includes("progress") || raw.includes("created") || raw.includes("claimed")) {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  if (raw.includes("request") || raw.includes("pending") || raw.includes("wait") || raw.includes("review")) {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  if (raw.includes("fail") || raw.includes("reject") || raw.includes("error") || raw.includes("block")) {
    return "border-red-200 bg-red-50 text-red-700";
  }
  return "border-slate-200 bg-slate-100 text-slate-600";
}

function artifactLabel(type: string) {
  return type.replaceAll("_", " ").toUpperCase();
}

function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_10px_34px_rgba(15,23,42,0.06)] ${className}`}>{children}</section>;
}

function PanelHeader({ icon, title, right }: { icon: BrandIconName; title: string; right?: React.ReactNode }) {
  return (
    <div className="flex min-h-12 items-center justify-between gap-3 border-b border-slate-200 px-4">
      <div className="flex items-center gap-2">
        <BrandIcon className="text-blue-600" name={icon} size={17} />
        <h2 className="text-[13px] font-semibold text-slate-950">{title}</h2>
      </div>
      {right}
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="dp-sidebar hidden h-screen flex-col lg:flex">
      <Link className="flex items-center gap-3" href="/app">
        <span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-sm font-black shadow-[0_10px_28px_rgba(37,99,235,0.35)]">D</span>
        <span className="text-lg font-semibold">Dipeen</span>
      </Link>
      <nav className="mt-7 space-y-1">
        {navItems.map((item) => (
          <Link
            className={`flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition ${
              item.label === "Runs" ? "dp-active" : "text-slate-300 hover:bg-white/[0.08] hover:text-white"
            }`}
            href={resolveDipeenNavHref(item)}
            key={item.label}
          >
            <BrandIcon name={item.icon} size={16} />
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.05] p-3">
        <p className="text-[12px] font-semibold text-white">Run Workbench</p>
        <p className="mt-1 text-[11px] text-slate-400">events, artifacts, claims</p>
      </div>
    </aside>
  );
}

function RunList({
  runs,
  selectedRunId,
  onSelect,
}: {
  runs: ControlPlaneRun[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}) {
  return (
    <Panel className="flex max-h-[calc(100vh-112px)] min-h-[520px] flex-col">
      <PanelHeader icon="play" title="Runs" right={<span className="text-[11px] text-slate-500">{runs.length} total</span>} />
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {runs.length === 0 && <p className="px-2 py-8 text-sm text-slate-400">No provider run has been reconciled into Dipeen yet.</p>}
        {runs.map((run) => (
          <button
            className={`w-full rounded-lg border px-3 py-3 text-left transition ${
              selectedRunId === run.run_id ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-slate-50 hover:border-blue-200"
            }`}
            key={run.run_id}
            onClick={() => onSelect(run.run_id)}
            type="button"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[12px] font-semibold text-slate-900">{shortId(run.run_id, 14)}</span>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] ${statusTone(run.state)}`}>{run.state}</span>
            </div>
            <p className="mt-2 truncate text-[12px] text-slate-500">{run.identity_id}</p>
            <p className="mt-1 truncate font-mono text-[11px] text-slate-400">{run.task_id}</p>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function RunSummary({ run, task }: { run: ControlPlaneRun | null; task?: Task }) {
  return (
    <Panel>
      <PanelHeader
        icon="inspect"
        title="Run Evidence"
        right={run ? <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone(run.state)}`}>{run.state}</span> : null}
      />
      <div className="grid gap-4 p-4 md:grid-cols-4">
        {[
          ["Run ID", run?.run_id],
          ["Task", task?.subject ?? run?.task_id],
          ["Worker", run?.identity_id],
          ["Started", formatTime(run?.created_at)],
        ].map(([label, value]) => (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3" key={label}>
            <p className="text-[11px] font-semibold uppercase text-slate-400">{label}</p>
            <p className="mt-2 truncate text-sm font-semibold text-slate-900">{value ?? "-"}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function EventStream({ events }: { events: ControlPlaneEvent[] }) {
  return (
    <Panel className="min-h-[380px]">
      <PanelHeader icon="workflow" title="Canonical Event Stream" right={<span className="text-[11px] text-emerald-600">SSE/WS invalidated</span>} />
      <div className="max-h-[500px] overflow-auto p-4">
        {events.length === 0 && <p className="py-10 text-sm text-slate-400">No events for the selected run.</p>}
        {events.slice(-24).reverse().map((event) => (
          <div className="grid grid-cols-[76px_minmax(0,1fr)_120px] gap-3 border-b border-slate-100 py-2 last:border-b-0" key={event.event_id}>
            <span className="font-mono text-[11px] text-slate-400">{formatTime(event.created_at)}</span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">{event.event_type}</p>
              <p className="truncate text-[12px] text-slate-500">{event.message || "No message payload"}</p>
            </div>
            <span className="truncate text-right text-[11px] text-slate-500">{event.producer}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ArtifactGrid({ artifacts }: { artifacts: ControlPlaneArtifact[] }) {
  return (
    <Panel className="min-h-[380px]">
      <PanelHeader icon="database" title="Artifacts" right={<span className="text-[11px] text-slate-500">{artifacts.length} fetched by REST</span>} />
      <div className="grid gap-3 p-4 md:grid-cols-2">
        {artifacts.length === 0 && <p className="col-span-full py-10 text-sm text-slate-400">No artifacts for the selected run.</p>}
        {artifacts.map((artifact) => (
          <article className="rounded-lg border border-slate-200 bg-slate-50 p-3" key={artifact.artifact_id}>
            <div className="flex items-center justify-between gap-3">
              <p className="truncate text-sm font-semibold text-slate-900">{artifactLabel(artifact.type)}</p>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] ${statusTone(artifact.status)}`}>{artifact.status}</span>
            </div>
            <p className="mt-2 min-h-9 text-[12px] leading-5 text-slate-600">{artifact.summary || artifact.title}</p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
              <span className="truncate">Producer: {artifact.producer.identity}</span>
              <span className="truncate text-right">Evidence: {artifact.evidence.filter((item) => item.passed).length}/{artifact.evidence.length}</span>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}

function ClaimsPanel({ claims }: { claims: StateClaim[] }) {
  return (
    <Panel>
      <PanelHeader icon="check" title="State Claims" />
      <div className="space-y-2 p-4">
        {claims.length === 0 && <p className="py-6 text-sm text-slate-400">No provider state claims for this run.</p>}
        {claims.slice(0, 8).map((claim) => (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={claim.claim_id}>
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-[12px] font-semibold text-slate-900">{claim.claimed_state}</span>
              <span className="text-[11px] text-slate-400">{formatTime(claim.created_at)}</span>
            </div>
            <p className="mt-1 truncate text-[12px] text-slate-500">{claim.producer}: {claim.message}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function RunWorkbench() {
  const { summary, error: summaryError } = useControlPlaneSummary();
  const { tasks } = useTasks();
  const { runs, loading: runsLoading, error: runsError } = useRuns();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedRunId && runs.length > 0) setSelectedRunId(runs[0].run_id);
  }, [runs, selectedRunId]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.run_id === selectedRunId) ?? runs[0] ?? null,
    [runs, selectedRunId],
  );
  const selectedTask = useMemo(
    () => tasks.find((task) => task.task_id === selectedRun?.task_id),
    [tasks, selectedRun?.task_id],
  );
  const { events, error: eventsError } = useEvents({ runId: selectedRun?.run_id, tail: 100 });
  const { artifacts, error: artifactsError } = useArtifacts({ runId: selectedRun?.run_id });
  const { claims, error: claimsError } = useStateClaims({ runId: selectedRun?.run_id });
  const { permissions, approvePermission, rejectPermission } = usePermissions("requested");
  const { candidates, promoteCandidate, rejectCandidate } = useMemoryCandidates("pending");

  const errors = [summaryError, runsError, eventsError, artifactsError, claimsError].filter(Boolean);

  return (
    <div className="dp-app">
      <Sidebar />
      <main className="dp-page-main overflow-auto">
        <header className="dp-topbar sticky top-0 z-10 flex items-center justify-between px-6">
          <div>
            <p className="text-[12px] font-semibold text-blue-700">Dipeen Run Workbench</p>
            <h1 className="mt-1 text-xl font-semibold text-slate-950">Runtime execution, artifacts, and approvals</h1>
            <p className="mt-1 text-xs text-slate-500">
              Dipeen is the source of truth. Providers can only claim state until Dipeen reconciles it.
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-emerald-500" />Live</span>
            <span>{summary?.snapshot_at ? formatTime(summary.snapshot_at) : formatTime(new Date().toISOString())}</span>
            <Link className="rounded-lg border border-slate-200 px-3 py-2 font-medium text-slate-700" href="/app">Overview</Link>
          </div>
        </header>

        <div className="space-y-4 p-5">
          {errors.length > 0 && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {errors.join(" · ")}
            </div>
          )}
          {runsLoading && runs.length === 0 && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
              Loading canonical runs...
            </div>
          )}

          <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
            <RunList runs={runs} selectedRunId={selectedRun?.run_id ?? null} onSelect={setSelectedRunId} />
            <div className="space-y-4">
              <RunSummary run={selectedRun} task={selectedTask} />
              <EventStream events={events} />
              <ArtifactGrid artifacts={artifacts} />
            </div>
            <div className="space-y-4">
              <ClaimsPanel claims={claims} />
              <Panel>
                <PanelHeader icon="shield" title="Permission Queue" right={<span className="text-[11px] text-amber-600">{permissions.length} pending</span>} />
                <div className="space-y-2 p-4">
                  {permissions.length === 0 && <p className="py-6 text-sm text-slate-400">No approval requests.</p>}
                  {permissions.slice(0, 5).map((permission) => (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3" key={permission.permission_request_id}>
                      <p className="truncate text-sm font-semibold text-slate-900">{permission.action}</p>
                      <p className="mt-1 text-[12px] leading-5 text-slate-600">{permission.reason}</p>
                      <div className="mt-3 flex gap-2">
                        <button className="rounded bg-blue-600 px-2 py-1 text-[11px] font-medium text-white" onClick={() => void approvePermission(permission.permission_request_id)} type="button">Approve</button>
                        <button className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-600" onClick={() => void rejectPermission(permission.permission_request_id)} type="button">Reject</button>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel>
                <PanelHeader icon="layers" title="Memory Candidates" right={<span className="text-[11px] text-slate-500">{candidates.length} pending</span>} />
                <div className="space-y-2 p-4">
                  {candidates.length === 0 && <p className="py-6 text-sm text-slate-400">No proposed memory needs review.</p>}
                  {candidates.slice(0, 5).map((candidate) => (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3" key={candidate.memory_candidate_id}>
                      <p className="truncate text-[12px] font-semibold text-slate-900">{candidate.memory_type}</p>
                      <p className="mt-1 text-[12px] leading-5 text-slate-600">{candidate.proposed_content}</p>
                      <div className="mt-3 flex gap-2">
                        <button className="rounded bg-blue-600 px-2 py-1 text-[11px] font-medium text-white" onClick={() => void promoteCandidate(candidate.memory_candidate_id)} type="button">Promote</button>
                        <button className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-600" onClick={() => void rejectCandidate(candidate.memory_candidate_id)} type="button">Reject</button>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
