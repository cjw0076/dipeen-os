"use client";

import Link from "next/link";
import { useMemo } from "react";
import { dipeenNavItems, resolveDipeenNavHref } from "@/components/layout/dipeen-nav";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import { useChat } from "@/hooks/useChat";
import { useControlPlaneSummary } from "@/hooks/useControlPlaneSummary";
import { useMemoryCandidates } from "@/hooks/useMemoryCandidates";
import { useNatProductAlpha } from "@/hooks/useNatProductAlpha";
import { usePermissions } from "@/hooks/usePermissions";
import { useProjects } from "@/hooks/useProjects";
import { useTasks } from "@/hooks/useTasks";
import {
  DEFAULT_PRODUCT_PATH,
  EMPTY_PRODUCT_FLOW_SIGNALS,
  PRODUCT_FLOW_INVARIANTS,
  PRODUCT_FLOW_STAGES,
  buildProductFlowStates,
  productFlowProgress,
  type ProductFlowSignals,
  type ProductFlowStageId,
  type ProductFlowState,
} from "@/lib/user-flow";

export type ProductFlowCounts = {
  tasks: number;
  doneTasks: number;
  workers: number;
  proposals: number;
  queuedCommands: number;
  runs: number;
  events: number;
  artifacts: number;
  permissions: number;
  memoryCandidates: number;
};

const stageIcons: Record<ProductFlowStageId, BrandIconName> = {
  entry: "key",
  onboarding: "agent",
  control: "command",
  meeting: "meeting",
  "task-board": "board",
  worker: "workflow",
  "run-monitor": "play",
  "artifact-review": "database",
  permission: "shield",
  memory: "layers",
  completion: "graph",
};

function stateLabel(state: ProductFlowState) {
  if (state === "done") return "Done";
  if (state === "active") return "Active";
  if (state === "blocked") return "Blocked";
  return "Waiting";
}

function stateClass(state: ProductFlowState) {
  if (state === "done") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (state === "active") return "border-blue-200 bg-blue-50 text-blue-700";
  if (state === "blocked") return "border-red-200 bg-red-50 text-red-700";
  return "border-slate-200 bg-slate-50 text-slate-500";
}

function stateDotClass(state: ProductFlowState) {
  if (state === "done") return "bg-emerald-500";
  if (state === "active") return "bg-blue-500";
  if (state === "blocked") return "bg-red-500";
  return "bg-slate-300";
}

function hasEvent(events: Array<{ event_type: string }>, pattern: string) {
  return events.some((event) => event.event_type.toLowerCase().includes(pattern));
}

function isDoneCommand(state: string) {
  const raw = state.toLowerCase();
  return raw.includes("complete") || raw.includes("done") || raw.includes("fail");
}

function isQueuedOrRunningCommand(state: string) {
  const raw = state.toLowerCase();
  return raw.includes("queue") || raw.includes("lease") || raw.includes("run") || raw.includes("progress");
}

export function buildSignalsFromLiveState({
  hasWorkspace,
  tasks,
  messages,
  proposals,
  workers,
  commands,
  events,
  artifacts,
  permissions,
  memoryCandidates,
  goalProgress,
}: {
  hasWorkspace: boolean;
  tasks: Array<{ status: string }>;
  messages: unknown[];
  proposals: unknown[];
  workers: unknown[];
  commands: Array<{ state: string }>;
  events: Array<{ event_type: string; run_id: string | null }>;
  artifacts: Array<{ status: string; type: string }>;
  permissions: unknown[];
  memoryCandidates: Array<{ status: string }>;
  goalProgress?: { total: number; done: number; blocked: number };
}): ProductFlowSignals {
  const hasGoal = Boolean(goalProgress?.total || tasks.length || messages.length || proposals.length || commands.length);
  const hasQueuedCommand = commands.some((command) => isQueuedOrRunningCommand(command.state) || isDoneCommand(command.state));
  const hasRun = commands.some((command) => isDoneCommand(command.state) || isQueuedOrRunningCommand(command.state)) || events.some((event) => Boolean(event.run_id));
  const hasRunEvent = events.length > 0;
  const hasVerifiedArtifact = artifacts.some((artifact) => artifact.status.toLowerCase().includes("verified"));
  const hasPermissionReceipt =
    artifacts.some((artifact) => artifact.type.toLowerCase().includes("permission_receipt")) ||
    hasEvent(events, "permission.execut");
  const hasPromotedMemory = memoryCandidates.some((candidate) => candidate.status.toLowerCase().includes("promot"));
  const total = goalProgress?.total ?? tasks.length;
  const done = goalProgress?.done ?? tasks.filter((task) => task.status.toLowerCase().includes("done")).length;
  const blocked = goalProgress?.blocked ?? tasks.filter((task) => task.status.toLowerCase().includes("block")).length;

  return {
    ...EMPTY_PRODUCT_FLOW_SIGNALS,
    hasWorkspace,
    hasWorker: workers.length > 0,
    hasGoal,
    hasDiscussion: messages.length > 0,
    hasProposal: proposals.length > 0 || commands.length > 0,
    hasQueuedCommand,
    hasRun,
    hasRunEvent,
    hasArtifact: artifacts.length > 0,
    hasVerifiedArtifact,
    hasPendingPermission: permissions.length > 0,
    hasPermissionReceipt,
    hasMemoryCandidate: memoryCandidates.length > 0,
    hasPromotedMemory,
    goalComplete: total > 0 && done >= total && blocked === 0,
    hasBlocker: blocked > 0,
  };
}

export function ProductFlowSpine({
  signals,
  counts,
  compact = false,
}: {
  signals: ProductFlowSignals;
  counts?: ProductFlowCounts;
  compact?: boolean;
}) {
  const progress = productFlowProgress(signals);
  const states = buildProductFlowStates(signals);

  if (compact) {
    return (
      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_10px_34px_rgba(15,23,42,0.06)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div>
            <div className="flex items-center gap-2">
              <BrandIcon className="text-blue-600" name="workflow" size={17} />
              <h2 className="text-[13px] font-semibold text-slate-950">Product Path</h2>
            </div>
            <p className="mt-1 text-xs text-slate-500">Goal to verified completion. Web UI observes and gates; workers execute locally.</p>
          </div>
          <Link className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-blue-700 hover:border-blue-300" href="/flow">
            Open flow map
          </Link>
        </div>
        <div className="grid gap-2 p-4 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-11">
          {PRODUCT_FLOW_STAGES.map((stage) => {
            const state = states[stage.id];
            return (
              <Link className={`rounded-lg border px-3 py-2 ${stateClass(state)} hover:border-blue-300`} href={stage.href} key={stage.id}>
                <div className="flex items-center gap-2">
                  <span className={`size-2 rounded-full ${stateDotClass(state)}`} />
                  <span className="font-mono text-[10px]">{stage.index}</span>
                </div>
                <p className="mt-2 truncate text-[12px] font-semibold">{stage.title}</p>
              </Link>
            );
          })}
        </div>
        {counts && (
          <div className="grid grid-cols-3 gap-2 border-t border-slate-200 px-4 py-3 text-center text-[11px] text-slate-500 md:grid-cols-6">
            <span>{counts.workers} workers</span>
            <span>{counts.proposals} proposals</span>
            <span>{counts.queuedCommands} commands</span>
            <span>{counts.events} events</span>
            <span>{counts.artifacts} artifacts</span>
            <span>{counts.memoryCandidates} memory</span>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_10px_34px_rgba(15,23,42,0.06)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-[0.18em] text-blue-600">Web UI User Flow</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">Goal to verified team execution</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Dipeen Web UI coordinates communication, approval, observation, artifact review, permission gates, and memory review.
              Provider CLIs and OMO/Hermes run on local workers.
            </p>
          </div>
          <div className="min-w-[160px] rounded-xl border border-blue-200 bg-blue-50 p-4 text-blue-800">
            <p className="text-[11px] font-semibold uppercase">Flow progress</p>
            <p className="mt-1 text-3xl font-semibold">{progress.percent}%</p>
            <p className="text-xs">{progress.done} / {progress.total} stages done</p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {PRODUCT_FLOW_STAGES.map((stage) => {
          const state = states[stage.id];
          return (
            <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_10px_34px_rgba(15,23,42,0.04)]" key={stage.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className={`grid size-10 place-items-center rounded-lg border ${stateClass(state)}`}>
                    <BrandIcon name={stageIcons[stage.id]} size={18} />
                  </span>
                  <div>
                    <p className="font-mono text-[11px] text-slate-400">Phase {stage.index}</p>
                    <h2 className="text-base font-semibold text-slate-950">{stage.title}</h2>
                  </div>
                </div>
                <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${stateClass(state)}`}>
                  {stateLabel(state)}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{stage.summary}</p>
              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-[11px] font-semibold uppercase text-slate-400">Outcome</p>
                <p className="mt-1 text-sm text-slate-700">{stage.outcome}</p>
              </div>
              <div className="mt-4 flex items-center justify-between gap-3 text-xs">
                <span className="rounded-full bg-slate-100 px-2 py-1 font-medium text-slate-600">{stage.owner}</span>
                <Link className="font-semibold text-blue-700 hover:text-blue-900" href={stage.href}>
                  Open {stage.surface}
                </Link>
              </div>
            </article>
          );
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_10px_34px_rgba(15,23,42,0.04)]">
          <div className="flex items-center gap-2">
            <BrandIcon className="text-blue-600" name="play" size={17} />
            <h2 className="text-[13px] font-semibold text-slate-950">Default Public v0 Path</h2>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            {DEFAULT_PRODUCT_PATH.map((item, index) => (
              <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={item}>
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-blue-600 text-[10px] font-semibold text-white">{index + 1}</span>
                <span className="text-sm text-slate-700">{item}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_10px_34px_rgba(15,23,42,0.04)]">
          <div className="flex items-center gap-2">
            <BrandIcon className="text-blue-600" name="shield" size={17} />
            <h2 className="text-[13px] font-semibold text-slate-950">Execution Invariants</h2>
          </div>
          <div className="mt-4 space-y-2">
            {PRODUCT_FLOW_INVARIANTS.map((item) => (
              <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={item}>
                <BrandIcon className="shrink-0 text-emerald-600" name="check" size={16} />
                <span className="text-sm text-slate-700">{item}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function FlowSidebar({ roomId }: { roomId: string }) {
  return (
    <aside className="dp-sidebar hidden h-screen flex-col lg:flex">
      <Link className="flex items-center gap-3" href="/app">
        <span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-sm font-black shadow-[0_10px_28px_rgba(37,99,235,0.35)]">D</span>
        <span className="text-lg font-semibold">Dipeen</span>
      </Link>
      <nav className="mt-7 space-y-1">
        {dipeenNavItems.map((item) => {
          const href = resolveDipeenNavHref(item, roomId);
          const active = item.href === "/flow";
          return (
            <Link
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition ${
                active ? "dp-active" : "text-slate-300 hover:bg-white/[0.08] hover:text-white"
              }`}
              href={href}
              key={item.label}
            >
              <BrandIcon name={item.icon} size={16} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.05] p-3">
        <p className="text-[12px] font-semibold text-white">Flow Contract</p>
        <p className="mt-1 text-[11px] text-slate-400">Web gates. Workers execute.</p>
      </div>
    </aside>
  );
}

export function ProductFlowDashboard() {
  const { summary, loading, error } = useControlPlaneSummary();
  const { currentProject } = useProjects();
  const { tasks } = useTasks();
  const roomId = currentProject?.room_id ?? "general";
  const { messages } = useChat(roomId);
  const { permissions } = usePermissions("requested");
  const { candidates } = useMemoryCandidates("pending");
  const { proposals, workers, commands, error: natError } = useNatProductAlpha(roomId);

  const events = summary?.latest_events ?? [];
  const artifacts = summary?.latest_artifacts ?? [];
  const workerRows = workers.length ? workers : summary?.workers ?? [];
  const proposalRows = proposals.length ? proposals : summary?.pending_proposals ?? [];
  const commandRows = commands.length ? commands : summary?.queued_commands ?? [];
  const permissionRows = permissions.length ? permissions : summary?.pending_permissions ?? [];
  const candidateRows = candidates.length ? candidates : summary?.memory_candidates ?? [];

  const signals = useMemo(
    () =>
      buildSignalsFromLiveState({
        hasWorkspace: Boolean(summary?.team_id || currentProject?.id),
        tasks,
        messages,
        proposals: proposalRows,
        workers: workerRows,
        commands: commandRows,
        events,
        artifacts,
        permissions: permissionRows,
        memoryCandidates: candidateRows,
        goalProgress: summary?.goal_progress,
      }),
    [artifacts, candidateRows, commandRows, currentProject?.id, events, messages, permissionRows, proposalRows, summary?.goal_progress, summary?.team_id, tasks, workerRows],
  );

  const counts: ProductFlowCounts = {
    tasks: tasks.length,
    doneTasks: summary?.goal_progress.done ?? tasks.filter((task) => task.status.toLowerCase().includes("done")).length,
    workers: workerRows.length,
    proposals: proposalRows.length,
    queuedCommands: commandRows.filter((command) => isQueuedOrRunningCommand(command.state)).length,
    runs: summary?.active_runs.length ?? 0,
    events: events.length,
    artifacts: artifacts.length,
    permissions: permissionRows.length,
    memoryCandidates: candidateRows.length,
  };

  return (
    <div className="dp-app">
      <FlowSidebar roomId={roomId} />
      <main className="dp-page-main overflow-auto">
        <header className="dp-topbar sticky top-0 z-10 flex items-center justify-between px-6">
          <div>
            <p className="text-[12px] font-semibold text-blue-700">Dipeen Product Flow</p>
            <h1 className="mt-1 text-xl font-semibold text-slate-950">{currentProject?.name ?? "Workspace"} execution map</h1>
            <p className="mt-1 text-xs text-slate-500">Canonical user flow wired to NAT control-plane signals.</p>
          </div>
          <Link className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white" href="/app">
            Back to Control Tower
          </Link>
        </header>
        <div className="space-y-4 p-5">
          {loading && !summary && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
              Loading control-plane flow signals...
            </div>
          )}
          {(error || natError) && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              {error ? `Summary API: ${error}` : null}
              {error && natError ? " · " : null}
              {natError ? `NAT API: ${natError}` : null}
            </div>
          )}
          <ProductFlowSpine counts={counts} signals={signals} />
        </div>
      </main>
    </div>
  );
}
