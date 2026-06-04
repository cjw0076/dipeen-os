"use client";

import Link from "next/link";
import { DipeenAppShell } from "@/components/layout/DipeenAppShell";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import { useControlPlaneSummary } from "@/hooks/useControlPlaneSummary";
import { useNatProductAlpha } from "@/hooks/useNatProductAlpha";
import { useWorkspaceSpec } from "@/hooks/useWorkspaceSpec";
import type { WorkerCommand, WorkerInfo } from "@/lib/api";

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function parseCapability(capabilities: string[], prefix: string) {
  const found = capabilities.find((capability) => capability.startsWith(`${prefix}.`));
  return found ? found.slice(prefix.length + 1) : null;
}

function collapseErrors(values: Array<string | null | undefined>) {
  const unique = Array.from(new Set(values.filter((value): value is string => Boolean(value)).map((value) => value.replace(/^Error:\s*/, ""))));
  if (unique.length === 0) return null;
  if (unique.length === 1) return unique[0];
  return `${unique[0]} (${unique.length} requests affected.)`;
}

function workerState(worker: WorkerInfo, commands: WorkerCommand[]) {
  if (commands.some((command) => command.lease_owner === worker.worker_id && /lease|run|progress/i.test(command.state))) return "working";
  const last = new Date(worker.last_heartbeat);
  if (Number.isNaN(last.getTime()) || Date.now() - last.getTime() > 5 * 60_000) return "offline";
  return worker.state || "reported";
}

function OfficePanel({
  children,
  className,
  icon,
  title,
}: {
  children: React.ReactNode;
  className?: string;
  icon: BrandIconName;
  title: string;
}) {
  return (
    <section className={cn("rounded-2xl border border-[var(--ds-border)] bg-white p-4 shadow-[var(--ds-shadow-card)]", className)}>
      <div className="mb-4 flex items-center gap-2">
        <span className="grid size-8 place-items-center rounded-lg bg-[var(--ds-primary-soft)] text-[var(--ds-primary)]">
          <BrandIcon name={icon} size={17} />
        </span>
        <h2 className="text-sm font-bold text-[var(--ds-text)]">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function EmptyLine({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-sm text-[var(--ds-text-muted)]">{children}</p>;
}

export function BrandOffice() {
  const { summary, error: summaryError, refetch: refetchSummary } = useControlPlaneSummary();
  const { spec, error: specError, refetch: refetchSpec } = useWorkspaceSpec();
  const { workers, commands, error: natError, refetch: refetchNat } = useNatProductAlpha("general");

  const visibleWorkers = workers.length ? workers : summary?.workers ?? [];
  const visibleCommands = commands.length ? commands : summary?.queued_commands ?? [];
  const workspaceName = spec?.workspace_id ?? summary?.team_id ?? "Dipeen workspace";
  const safeMode = spec?.policies.permission_executor_mode ?? "dry_run";
  const errorMessage = collapseErrors([summaryError, specError, natError]);
  const activeCommands = visibleCommands.filter((command) => /queued|lease|run|progress/i.test(command.state));

  const refresh = () => {
    void Promise.allSettled([refetchSummary(), refetchSpec(), refetchNat()]);
  };

  return (
    <DipeenAppShell
      activeLabels={["Office"]}
      eyebrow="Dipeen Office"
      footerCaption="brand workspace"
      right={(
        <>
          <Link className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shadow-sm" href="/app">
            Open Control Room
          </Link>
          <button className="rounded-lg bg-[var(--ds-primary)] px-3 py-2 text-xs font-bold text-white shadow-sm" onClick={refresh} type="button">
            Refresh
          </button>
        </>
      )}
      subtitle={`${spec?.mode ?? "workspace spec loading"} · ${workspaceName} · ${summary?.snapshot_at ? formatTime(summary.snapshot_at) : "waiting for HQ state"}`}
      title="Dipeen Office"
      visibleNavLabels={["Overview", "Office"]}
      workspaceName={workspaceName}
    >
      <div className="space-y-5 p-4 lg:p-6">
        {errorMessage && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
            {errorMessage}
          </div>
        )}

        <section className="overflow-hidden rounded-3xl border border-[#e9dcc8] bg-[#fffaf0] shadow-[0_24px_70px_rgba(69,43,24,0.12)]">
          <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="p-6 lg:p-8">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#9a6b32]">Accountable Agent Teams</p>
              <h1 className="mt-3 max-w-3xl text-3xl font-black leading-tight text-[#1f2937] lg:text-5xl">
                A team office where commands, evidence, permissions, and memory stay accountable.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-[#54606f]">
                Dipeen is the control plane. Provider CLIs and worker harnesses run locally; HQ records the command queue, event log, artifacts, permission decisions, and reconciled state.
              </p>
              <div className="mt-6 flex flex-wrap gap-2">
                <span className="rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-xs font-bold text-emerald-700">{safeMode}</span>
                <span className="rounded-full border border-blue-200 bg-white px-3 py-1.5 text-xs font-bold text-blue-700">{visibleWorkers.length} workers reported</span>
                <span className="rounded-full border border-amber-200 bg-white px-3 py-1.5 text-xs font-bold text-amber-700">{summary?.pending_permissions.length ?? 0} permission requests</span>
              </div>
            </div>
            <div className="border-t border-[#e9dcc8] bg-white/65 p-5 lg:border-l lg:border-t-0">
              <div className="grid gap-3">
                {[
                  ["Source of truth", "Dipeen reconciles provider claims before UI state is trusted."],
                  ["BYOK workers", "Provider authentication stays on teammate machines."],
                  ["Human gates", "Risky side effects wait in Permission Inbox."],
                ].map(([title, body]) => (
                  <div className="rounded-2xl border border-[#ecd9bd] bg-white p-4 shadow-sm" key={title}>
                    <p className="text-sm font-bold text-[#1f2937]">{title}</p>
                    <p className="mt-1 text-xs leading-5 text-[#647084]">{body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <OfficePanel icon="agent" title="Team Presence">
            <div className="grid gap-3 md:grid-cols-2">
              {visibleWorkers.length === 0 && <EmptyLine>No workers reported by /api/workers yet.</EmptyLine>}
              {visibleWorkers.map((worker) => {
                const role = parseCapability(worker.capabilities, "role") ?? "role not reported";
                const provider = parseCapability(worker.capabilities, "provider") ?? "provider not reported";
                const state = workerState(worker, visibleCommands);
                return (
                  <article className="rounded-xl border border-slate-200 bg-slate-50 p-3" key={worker.worker_id}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold text-slate-950">{worker.worker_id}</p>
                        <p className="mt-1 text-xs text-slate-500">{role} · {provider}</p>
                      </div>
                      <span className="rounded-full border border-blue-200 bg-white px-2 py-0.5 text-[11px] font-bold text-blue-700">{state}</span>
                    </div>
                    <p className="mt-2 text-[11px] text-slate-400">heartbeat {formatTime(worker.last_heartbeat)}</p>
                  </article>
                );
              })}
            </div>
          </OfficePanel>

          <OfficePanel icon="workflow" title="Workspace Shape">
            <dl className="grid gap-3 text-sm">
              <div className="flex justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                <dt className="text-slate-500">Layout</dt>
                <dd className="font-bold text-slate-800">{spec?.ui.layout ?? "not loaded"}</dd>
              </div>
              <div className="flex justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                <dt className="text-slate-500">Mode</dt>
                <dd className="font-bold text-slate-800">{spec?.mode ?? "not loaded"}</dd>
              </div>
              <div className="flex justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                <dt className="text-slate-500">Active commands</dt>
                <dd className="font-bold text-slate-800">{activeCommands.length}</dd>
              </div>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              {spec?.ui.panels.length ? spec.ui.panels.map((panel) => (
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-bold text-slate-600" key={panel}>{panel}</span>
              )) : <EmptyLine>No UI panels reported by TeamWorkspaceSpec.</EmptyLine>}
            </div>
          </OfficePanel>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <OfficePanel icon="check" title="System Health">
            <div className="space-y-2">
              {summary?.system_health.length ? summary.system_health.map((item) => (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={item.id}>
                  <div className="flex justify-between gap-3">
                    <p className="text-sm font-bold text-slate-800">{item.label}</p>
                    <span className="text-xs font-bold text-emerald-700">{item.status}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{item.detail}</p>
                </div>
              )) : <EmptyLine>No health rows returned by /api/control-plane/summary.</EmptyLine>}
            </div>
          </OfficePanel>

          <OfficePanel icon="database" title="Evidence Feed">
            <div className="space-y-2">
              {summary?.latest_artifacts.length ? summary.latest_artifacts.slice(0, 5).map((artifact) => (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={artifact.artifact_id}>
                  <p className="truncate text-sm font-bold text-slate-800">{artifact.title || artifact.type}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">{artifact.summary}</p>
                </div>
              )) : <EmptyLine>No artifacts returned by /api/artifacts yet.</EmptyLine>}
            </div>
          </OfficePanel>

          <OfficePanel icon="chat" title="Latest HQ Events">
            <div className="space-y-2">
              {summary?.latest_events.length ? summary.latest_events.slice(0, 6).map((event) => (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={event.event_id}>
                  <div className="flex justify-between gap-3">
                    <p className="truncate text-sm font-bold text-slate-800">{event.event_type}</p>
                    <span className="text-[11px] text-slate-400">{formatTime(event.created_at)}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">{event.message}</p>
                </div>
              )) : <EmptyLine>No events returned by /api/events yet.</EmptyLine>}
            </div>
          </OfficePanel>
        </div>
      </div>
    </DipeenAppShell>
  );
}
