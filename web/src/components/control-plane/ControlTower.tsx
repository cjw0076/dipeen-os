"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CommandPalette } from "@/components/command/CommandPalette";
import { DecisionNudgePanel } from "@/components/decisions/DecisionNudgePanel";
import { AssignmentRouting } from "@/components/control-plane/AssignmentRouting";
import { ProductFlowSpine, buildSignalsFromLiveState, type ProductFlowCounts } from "@/components/control-plane/ProductFlowMap";
import { dipeenNavItems, resolveDipeenNavHref } from "@/components/layout/dipeen-nav";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import { useChat } from "@/hooks/useChat";
import { useControlPlaneSummary } from "@/hooks/useControlPlaneSummary";
import { useMemoryCandidates } from "@/hooks/useMemoryCandidates";
import { useNatProductAlpha } from "@/hooks/useNatProductAlpha";
import { usePermissions } from "@/hooks/usePermissions";
import { useProjects } from "@/hooks/useProjects";
import { useTasks } from "@/hooks/useTasks";
import { useUsage } from "@/hooks/useUsage";
import { useWorkspaceSpec } from "@/hooks/useWorkspaceSpec";
import { api, getApiBaseUrl, type CommandProposal, type ControlPlaneArtifact, type ControlPlaneEvent, type ControlPlaneRun, type PaletteCommand, type PermissionApproveResult, type Task, type WorkerCommand, type WorkerInfo } from "@/lib/api";

const navItems = dipeenNavItems;

type FocusKey = "overview" | "workers" | "routing" | "evidence" | "approvals";

const focusMeta: Record<FocusKey, { label: string; icon: BrandIconName; description: string }> = {
  overview: { label: "Overview", icon: "command", description: "팀 상태 전체를 한 번에 확인합니다." },
  workers: { label: "Workers", icon: "workflow", description: "연결된 로컬 worker와 실행 중인 CLI command를 봅니다." },
  routing: { label: "Routing", icon: "spark", description: "작업을 제안하고 어떤 worker가 받을지 미리 봅니다." },
  evidence: { label: "Evidence", icon: "database", description: "worker가 제출한 artifact와 검증 증거를 확인합니다." },
  approvals: { label: "Approvals", icon: "shield", description: "사람 승인이 필요한 요청만 집중해서 처리합니다." },
};

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function formatRelative(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

function statusTone(status?: string | null) {
  const raw = (status ?? "").toLowerCase();
  if (raw.includes("done") || raw.includes("complete") || raw.includes("verified") || raw.includes("healthy") || raw.includes("idle")) {
    return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  }
  if (raw.includes("run") || raw.includes("progress") || raw.includes("work")) return "bg-blue-50 text-blue-700 ring-blue-200";
  if (raw.includes("wait") || raw.includes("permission") || raw.includes("pending") || raw.includes("ready")) return "bg-amber-50 text-amber-700 ring-amber-200";
  if (raw.includes("fail") || raw.includes("reject") || raw.includes("block") || raw.includes("error")) return "bg-red-50 text-red-700 ring-red-200";
  return "bg-slate-100 text-slate-600 ring-slate-200";
}

function artifactLabel(type: string) {
  return type.replaceAll("_", " ").toUpperCase();
}

function panelTitle(icon: BrandIconName, title: string, action?: string) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
      <div className="flex items-center gap-2">
        <BrandIcon className="text-blue-600" name={icon} size={17} />
        <h2 className="text-[13px] font-semibold text-slate-950">{title}</h2>
      </div>
      {action && <span className="text-[11px] font-medium text-blue-600">{action}</span>}
    </div>
  );
}

function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_10px_34px_rgba(15,23,42,0.06)] ${className}`}>{children}</section>;
}

function EmptyState({ text }: { text: string }) {
  return <p className="px-4 py-6 text-sm text-slate-400">{text}</p>;
}

function commandStateTone(state?: string | null) {
  const raw = (state ?? "").toLowerCase();
  if (raw.includes("run") || raw.includes("lease")) return "bg-blue-50 text-blue-700 ring-blue-200";
  if (raw.includes("queue")) return "bg-amber-50 text-amber-700 ring-amber-200";
  if (raw.includes("complete") || raw.includes("done")) return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  if (raw.includes("fail") || raw.includes("cancel")) return "bg-red-50 text-red-700 ring-red-200";
  return "bg-slate-100 text-slate-600 ring-slate-200";
}

function ProductionSignalBar({
  workers,
  commands,
  artifacts,
  permissions,
  tasks,
  workspaceId,
  workspaceMode,
  panelCount,
  showDryRunBanner,
  activeFocus,
  onFocus,
}: {
  workers: WorkerInfo[];
  commands: WorkerCommand[];
  artifacts: ControlPlaneArtifact[];
  permissions: ReturnType<typeof usePermissions>["permissions"];
  tasks: Task[];
  workspaceId?: string;
  workspaceMode?: string;
  panelCount?: number;
  showDryRunBanner?: boolean;
  activeFocus: FocusKey;
  onFocus: (focus: FocusKey) => void;
}) {
  const runningCommands = commands.filter((command) => {
    const state = command.state.toLowerCase();
    return state.includes("run") || state.includes("lease") || state.includes("queue");
  });
  const ownedTasks = tasks.filter((task) => task.assigned_agent_id || task.required_role);
  const metrics = [
    { key: "workers" as const, label: "Connected workers", value: workers.length, hint: workers.length ? "local nodes online" : "no worker yet", tone: "text-blue-700" },
    { key: "routing" as const, label: "Owned work", value: ownedTasks.length, hint: "assigned or role-routed", tone: "text-violet-700" },
    { key: "workers" as const, label: "Local CLI runs", value: runningCommands.length, hint: "queued / leased / running", tone: "text-amber-700" },
    { key: "evidence" as const, label: "Evidence", value: artifacts.length, hint: "artifacts from workers", tone: "text-emerald-700" },
    { key: "approvals" as const, label: "Needs approval", value: permissions.length, hint: "human gate", tone: "text-red-700" },
  ];

  return (
    <section className="rounded-xl border border-blue-100 bg-gradient-to-r from-white via-[#fffaf0] to-white p-4 shadow-[0_12px_38px_rgba(37,99,235,0.08)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-wide text-blue-700">Production Control Room</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-950">팀 상태, 실행 경계, 증거, 승인을 한 화면에서 봅니다.</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Host spec: <span className="font-mono">{workspaceId ?? "loading"}</span> · {workspaceMode ?? "team"} · {panelCount ?? 0} panels
          </p>
        </div>
        {showDryRunBanner !== false && (
          <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[12px] font-semibold text-emerald-800">
            SAFE MODE: dry_run · no PR / push / deploy by default
          </div>
        )}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {metrics.map((metric) => (
          <button
            aria-pressed={activeFocus === metric.key}
            className={`rounded-lg border px-3 py-3 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-[0_14px_30px_rgba(37,99,235,0.14)] ${
              activeFocus === metric.key ? "border-blue-400 bg-blue-50 ring-2 ring-blue-100" : "border-slate-200 bg-white"
            }`}
            key={metric.label}
            onClick={() => onFocus(metric.key)}
            type="button"
          >
            <p className="text-[11px] font-medium uppercase text-slate-400">{metric.label}</p>
            <p className={`mt-1 text-2xl font-semibold ${metric.tone}`}>{metric.value}</p>
            <p className="mt-1 truncate text-[11px] text-slate-500">{metric.hint}</p>
          </button>
        ))}
      </div>
    </section>
  );
}

function FocusActionRail({
  activeFocus,
  onFocus,
  onRefresh,
  refreshing,
  counts,
}: {
  activeFocus: FocusKey;
  onFocus: (focus: FocusKey) => void;
  onRefresh: () => void;
  refreshing: boolean;
  counts: Record<FocusKey, number>;
}) {
  const active = focusMeta[activeFocus];
  const actionCopy: Record<FocusKey, string> = {
    overview: "전체 flow를 보고 다음 병목을 찾습니다.",
    workers: "worker heartbeat와 leased command를 확인합니다.",
    routing: "작업 제안과 라우팅 미리보기를 조정합니다.",
    evidence: "artifact 검증 결과를 Run Workbench에서 이어서 봅니다.",
    approvals: "승인 요청을 처리해 다음 command를 열어줍니다.",
  };

  return (
    <section className="grid gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-[0_10px_34px_rgba(15,23,42,0.06)] xl:grid-cols-[1fr_auto]">
      <div className="flex min-w-0 flex-wrap gap-2">
        {(Object.keys(focusMeta) as FocusKey[]).map((key) => {
          const item = focusMeta[key];
          const selected = activeFocus === key;
          return (
            <button
              aria-pressed={selected}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition ${
                selected ? "border-blue-500 bg-blue-600 text-white shadow-[0_10px_22px_rgba(37,99,235,0.22)]" : "border-slate-200 bg-slate-50 text-slate-700 hover:border-blue-200 hover:bg-blue-50"
              }`}
              key={key}
              onClick={() => onFocus(key)}
              type="button"
            >
              <BrandIcon name={item.icon} size={15} />
              <span>{item.label}</span>
              <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${selected ? "bg-white/20 text-white" : "bg-white text-slate-500 ring-1 ring-slate-200"}`}>
                {counts[key]}
              </span>
            </button>
          );
        })}
      </div>
      <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-slate-200 bg-[#fffaf0] px-3 py-2 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-semibold text-slate-950">{active.label} focus</p>
          <p className="truncate text-[11px] text-slate-500">{active.description} {actionCopy[activeFocus]}</p>
        </div>
        <button
          className="shrink-0 rounded-lg border border-blue-200 bg-white px-3 py-2 text-xs font-semibold text-blue-700 shadow-sm transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={refreshing}
          onClick={onRefresh}
          type="button"
        >
          {refreshing ? "Refreshing..." : "Refresh live state"}
        </button>
      </div>
    </section>
  );
}

function JoinInvitePanel({
  teamId,
  roomId,
  projectName,
  workers,
}: {
  teamId: string | null;
  roomId: string;
  projectName: string;
  workers: WorkerInfo[];
}) {
  const [invite, setInvite] = useState<{ code: string; link: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const apiBase = getApiBaseUrl();
  const launcherCommand = `dipeen worker --remote ${apiBase} --worker-id <your-machine> --cap claude --cap git.diff`;

  const createInvite = async () => {
    if (!teamId) {
      setLocalError("Team is not ready. Bootstrap a project/team first.");
      return;
    }
    setBusy(true);
    setLocalError(null);
    try {
      const result = await api.teams.invite(teamId);
      const link = typeof window !== "undefined" ? `${window.location.origin}/onboarding?code=${result.code}` : result.join_url;
      setInvite({ code: result.code, link });
      await navigator.clipboard?.writeText(link).catch(() => {});
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const copyLauncher = () => {
    void navigator.clipboard?.writeText(launcherCommand).catch(() => {});
  };

  return (
    <Panel className="min-h-[258px]">
      {panelTitle("agent", "Join / Invite", "team workspace")}
      <div className="space-y-4 p-4">
        <div>
          <p className="text-sm font-semibold text-slate-950">{projectName}</p>
          <p className="mt-1 text-xs text-slate-500">Room <span className="font-mono">{roomId}</span> · {workers.length} worker nodes connected</p>
        </div>
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-3">
          <p className="text-[11px] font-semibold uppercase text-blue-700">Worker launcher</p>
          <code className="mt-2 block break-all rounded-md bg-white px-3 py-2 text-[11px] text-slate-700 ring-1 ring-blue-100">{launcherCommand}</code>
          <button className="mt-3 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white" onClick={copyLauncher} type="button">
            Copy launcher command
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm disabled:opacity-60" disabled={busy} onClick={createInvite} type="button">
            {busy ? "Creating invite..." : "Create invite link"}
          </button>
          {invite && <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">{invite.code}</span>}
        </div>
        {invite && <p className="break-all text-[11px] text-slate-500">{invite.link}</p>}
        {localError && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{localError}</p>}
      </div>
    </Panel>
  );
}

function DemoModePanel({ mode }: { mode?: string }) {
  return (
    <Panel className="min-h-[258px]">
      {panelTitle("spark", "Demo Panel", mode === "public_demo" ? "public demo" : "workspace")}
      <div className="space-y-3 p-4">
        <div className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-3">
          <p className="text-sm font-semibold text-violet-900">Public demo shell</p>
          <p className="mt-1 text-xs leading-5 text-violet-700">
            Host CLI가 만든 TeamWorkspaceSpec 기준으로 Join, worker, routing, artifact, permission 화면만 노출합니다.
          </p>
        </div>
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3">
          <p className="text-[11px] font-semibold uppercase text-emerald-800">Execution policy</p>
          <p className="mt-1 text-xs text-emerald-700">dry_run 기본값. PR, push, deploy, secret read는 사람이 승인해도 worker policy가 한 번 더 막습니다.</p>
        </div>
      </div>
    </Panel>
  );
}

function WorkerStatusPanel({ workers, commands }: { workers: WorkerInfo[]; commands: WorkerCommand[] }) {
  const activeByWorker = new Map<string, WorkerCommand[]>();
  for (const command of commands) {
    if (!command.lease_owner) continue;
    const rows = activeByWorker.get(command.lease_owner) ?? [];
    rows.push(command);
    activeByWorker.set(command.lease_owner, rows);
  }

  return (
    <Panel className="min-h-[258px]">
      {panelTitle("workflow", "Worker Status", "local CLI layer")}
      <div className="space-y-3 p-4">
        {workers.length === 0 && (
          <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-4">
            <p className="text-sm font-semibold text-slate-800">No workers connected.</p>
            <p className="mt-1 text-xs text-slate-500">로컬 PC에서 worker launcher를 실행하면 capabilities와 workspace가 여기 표시됩니다.</p>
          </div>
        )}
        {workers.slice(0, 5).map((worker) => {
          const active = activeByWorker.get(worker.worker_id) ?? [];
          const workspaceLabel = worker.workspaces?.[0]?.repo ?? worker.workspaces?.[0]?.workspace_ref ?? "no workspace";
          return (
            <article className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3" key={worker.worker_id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-950">{worker.worker_id}</p>
                  <p className="mt-1 truncate text-[11px] text-slate-500">{workspaceLabel} · heartbeat {formatRelative(worker.last_heartbeat)}</p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ring-1 ${statusTone(worker.state)}`}>{worker.state}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {(worker.capabilities.length ? worker.capabilities : ["capabilities pending"]).slice(0, 5).map((capability) => (
                  <span className="rounded bg-white px-2 py-0.5 text-[10px] text-slate-500 ring-1 ring-slate-200" key={capability}>{capability}</span>
                ))}
              </div>
              {active.length > 0 && (
                <div className="mt-2 space-y-1">
                  {active.slice(0, 2).map((command) => (
                    <div className="flex items-center justify-between gap-2 rounded bg-white px-2 py-1 text-[11px]" key={command.command_id}>
                      <span className="truncate font-mono text-slate-600">{command.command_id}</span>
                      <span className={`rounded px-2 py-0.5 ring-1 ${commandStateTone(command.state)}`}>{command.state}</span>
                    </div>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </Panel>
  );
}

function taskBucket(task: Task) {
  const raw = task.status.toLowerCase();
  if (raw.includes("done") || raw.includes("complete")) return "DONE";
  if (raw.includes("progress") || raw.includes("running") || raw.includes("working")) return "RUNNING";
  if (raw.includes("block") || raw.includes("error") || raw.includes("cancel") || raw.includes("reject")) return "BLOCKED";
  return "READY";
}

function taskTone(task: Task) {
  const bucket = taskBucket(task);
  if (bucket === "DONE") return "bg-emerald-50 text-emerald-700";
  if (bucket === "RUNNING") return "bg-blue-50 text-blue-700";
  if (bucket === "BLOCKED") return "bg-red-50 text-red-700";
  return "bg-violet-50 text-violet-700";
}

function goalPercent(total: number, done: number) {
  if (!total) return 0;
  return Math.round((done / total) * 100);
}

function Sidebar({ roomId, workspaceName }: { roomId: string; workspaceName: string }) {
  return (
    <aside className="dp-sidebar hidden h-screen flex-col lg:flex">
      <Link className="flex items-center gap-3" href="/app">
        <span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-sm font-black shadow-[0_10px_28px_rgba(37,99,235,0.35)]">D</span>
        <span className="text-lg font-semibold">Dipeen</span>
      </Link>
      <nav className="mt-7 space-y-1">
        {navItems.map((item) => {
          const href = resolveDipeenNavHref(item, roomId);
          const active = item.label === "Overview";
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
        <p className="truncate text-[12px] font-semibold text-white">{workspaceName}</p>
        <p className="mt-1 text-[11px] text-slate-400">control-plane user</p>
      </div>
    </aside>
  );
}

function GoalProgress({ total, done, running, ready, waiting, blocked }: {
  total: number;
  done: number;
  running: number;
  ready: number;
  waiting: number;
  blocked: number;
}) {
  const percent = goalPercent(total, done);
  return (
    <Panel>
      {panelTitle("spark", "Goal Progress")}
      <div className="grid grid-cols-[1fr_96px] gap-4 p-4">
        <div>
          <p className="text-sm font-semibold text-slate-950">Project execution readiness</p>
          <p className="mt-1 text-xs text-slate-500">{done} / {total || 0} tasks completed</p>
          <div className="mt-5 grid grid-cols-5 gap-2">
            {[
              ["Total", total, "text-blue-700"],
              ["Done", done, "text-emerald-700"],
              ["Running", running, "text-blue-700"],
              ["Waiting", waiting || ready, "text-amber-700"],
              ["Blocked", blocked, "text-red-700"],
            ].map(([label, value, tone]) => (
              <div className="rounded-lg bg-slate-50 px-2 py-2 text-center" key={String(label)}>
                <p className={`text-base font-semibold ${tone}`}>{value}</p>
                <p className="mt-1 text-[10px] text-slate-500">{label}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="grid place-items-center">
          <div className="grid size-20 place-items-center rounded-full" style={{ background: `conic-gradient(#16a34a ${percent}%, #e5e7eb ${percent}% 100%)` }}>
            <div className="grid size-14 place-items-center rounded-full bg-white text-lg font-bold text-slate-950">{percent}%</div>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function SystemHealth({ items }: { items: Array<{ id: string; label: string; status: string; detail: string }> }) {
  return (
    <Panel>
      {panelTitle("shield", "System Health")}
      <div className="space-y-2 p-4">
        {items.length === 0 && <EmptyState text="No health checks reported." />}
        {items.map((item) => (
          <div className="flex items-center gap-3" key={item.id}>
            <span className={`size-2 rounded-full ${item.status === "healthy" ? "bg-emerald-500" : item.status === "waiting" ? "bg-amber-500" : "bg-red-500"}`} />
            <span className="min-w-0 flex-1 truncate text-sm text-slate-700">{item.label}</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] ring-1 ${statusTone(item.status)}`}>{item.status}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ActiveRuns({ runs }: { runs: ControlPlaneRun[] }) {
  return (
    <Panel>
      {panelTitle("play", "Active Runs")}
      <div className="space-y-3 p-4">
        {runs.length === 0 && <EmptyState text="No canonical runs recorded yet." />}
        {runs.slice(0, 4).map((run) => (
          <Link className="block rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 hover:border-blue-300" href="/dashboard" key={run.run_id}>
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[11px] text-slate-700">{run.run_id}</span>
              <span className={`rounded-full px-2 py-0.5 text-[10px] ring-1 ${statusTone(run.state)}`}>{run.state}</span>
            </div>
            <p className="mt-1 truncate text-[12px] text-slate-500">{run.identity_id} · {run.task_id}</p>
          </Link>
        ))}
      </div>
    </Panel>
  );
}

function approveTone(mode: PermissionApproveResult["executor_mode"]) {
  // dry_run/manual_handoff = side effect 없음(안전) → 초록. local_execute = 실제 실행 → 호박색 경고.
  return mode === "local_execute"
    ? "border-amber-300 bg-amber-50 text-amber-800"
    : "border-emerald-300 bg-emerald-50 text-emerald-800";
}

function ApproveReceiptBanner({ result }: { result: PermissionApproveResult }) {
  const safe = result.executor_mode !== "local_execute";
  const detail = result.command_id
    ? `${result.executor_mode} · execute command ${result.command_id} queued`
    : `${result.status} · review gate (no command)`;
  return (
    <div className={`mb-3 rounded-lg border px-3 py-2 text-[11px] ${approveTone(result.executor_mode)}`}>
      <p className="font-semibold">{safe ? "Approved — no real side effect" : "Approved — LIVE execute"}</p>
      <p className="mt-0.5 break-all">{detail}</p>
    </div>
  );
}

function PermissionInbox({
  permissions,
  lastApprove,
  onApprove,
  onReject,
}: {
  permissions: ReturnType<typeof usePermissions>["permissions"];
  lastApprove: PermissionApproveResult | null;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <Panel>
      {panelTitle("shield", "Permission Inbox")}
      <div className="p-4">
        <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-800">
          <p className="font-semibold">Safety boundary: approve does not mean push/deploy.</p>
          <p className="mt-0.5">Dipeen queues permission.execute; the worker returns a receipt. Default executor mode is dry_run.</p>
        </div>
        <p className="text-3xl font-semibold text-amber-600">{permissions.length}</p>
        <p className="text-xs text-slate-500">Awaiting your approval</p>
        <div className="mt-4 space-y-3">
          {lastApprove && <ApproveReceiptBanner result={lastApprove} />}
          {permissions.length === 0 && <p className="text-sm text-slate-400">No permission requests.</p>}
          {permissions.slice(0, 3).map((permission) => (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2" key={permission.permission_request_id}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-[12px] font-semibold text-slate-900">{permission.action}</p>
                <span className={`rounded px-2 py-0.5 text-[10px] ring-1 ${statusTone(permission.risk)}`}>{permission.risk}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-[11px] text-slate-600">{permission.reason}</p>
              <div className="mt-2 flex gap-2">
                <button className="rounded bg-blue-600 px-2 py-1 text-[11px] font-medium text-white" onClick={() => onApprove(permission.permission_request_id)} type="button">Approve</button>
                <button className="rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-600" onClick={() => onReject(permission.permission_request_id)} type="button">Reject</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function TaskBoard({ tasks }: { tasks: Task[] }) {
  return (
    <Panel className="min-h-[260px]">
      {panelTitle("board", "Task Board", "ownership")}
      <div className="p-4">
        {tasks.length === 0 ? (
          <EmptyState text="No tasks yet. Create a goal or start a meeting to generate task envelopes." />
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200">
            {tasks.slice(0, 8).map((task) => (
              <div className="grid grid-cols-[84px_minmax(0,1fr)_96px_104px] items-center gap-3 border-b border-slate-200 px-3 py-2 last:border-b-0" key={task.task_id}>
                <span className="font-mono text-[11px] text-slate-500">{task.task_id.slice(0, 8)}</span>
                <span className="min-w-0">
                  <span className="block truncate text-sm text-slate-800">{task.subject}</span>
                  <span className="block truncate text-[11px] text-slate-400">{task.prompt || "No prompt recorded"}</span>
                </span>
                <span className="truncate rounded bg-slate-50 px-2 py-1 text-center text-[10px] font-medium text-slate-600 ring-1 ring-slate-200">
                  {task.assigned_agent_id ? "assigned" : task.required_role ?? "unowned"}
                </span>
                <span className={`justify-self-end rounded-full px-2 py-0.5 text-[10px] font-semibold ${taskTone(task)}`}>{taskBucket(task)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function RunTimeline({ events }: { events: ControlPlaneEvent[] }) {
  return (
    <Panel className="min-h-[260px]">
      {panelTitle("workflow", "Run Timeline", "Live")}
      <div className="space-y-0 p-4">
        {events.length === 0 && <EmptyState text="No canonical events recorded yet." />}
        {events.slice(-8).reverse().map((event) => (
          <div className="grid grid-cols-[64px_minmax(0,1fr)_120px] gap-3 border-b border-slate-100 py-2 last:border-b-0" key={event.event_id}>
            <span className="font-mono text-[11px] text-slate-400">{formatTime(event.created_at)}</span>
            <span className="truncate text-sm text-slate-800">{event.event_type}</span>
            <span className="truncate text-[11px] text-slate-500">{event.producer}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// Distinguishes HQ-verified evidence from worker self-reported claims (Evidence First).
function evidenceSource(kind: string): "verified" | "reported" | "neutral" {
  if (kind.includes("_verified") || kind === "git_diff_exists") return "verified";
  if (kind.endsWith("_reported") || kind === "tests_passed") return "reported";
  return "neutral";
}

function readableEvidenceKind(kind: string): string {
  return kind.replace(/_verified$|_reported$/, "").replace(/_/g, " ").trim() || kind;
}

// A single evidence chip surfacing provenance: blue = Verified by Dipeen, amber = Reported by
// worker (unverified), emerald/red = neutral OK/Fail. A failed check stays red regardless.
function evidenceChip(item: { kind: string; passed: boolean }, key: string) {
  const source = evidenceSource(item.kind);
  const label = readableEvidenceKind(item.kind);
  if (!item.passed) {
    return <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-700" key={key} title="Check failed">{`Fail ${label}`}</span>;
  }
  if (source === "verified") {
    return <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700" key={key} title="Verified by Dipeen">{`✓ Verified · ${label}`}</span>;
  }
  if (source === "reported") {
    return <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700" key={key} title="Reported by worker — not independently verified">{`⚑ Reported · ${label}`}</span>;
  }
  return <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700" key={key}>{`OK ${label}`}</span>;
}

function LatestArtifacts({ artifacts }: { artifacts: ControlPlaneArtifact[] }) {
  return (
    <Panel className="min-h-[260px]">
      {panelTitle("database", "Evidence / Artifacts", "verified objects")}
      <div className="p-4">
        {artifacts.length === 0 && <EmptyState text="No artifacts reported yet." />}
        <div className="space-y-2">
          {artifacts.slice(0, 6).map((artifact) => (
            <Link className="grid grid-cols-[1fr_auto] gap-3 rounded-lg border border-slate-200 px-3 py-2 hover:border-blue-300" href="/dashboard" key={artifact.artifact_id}>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">{artifactLabel(artifact.type)}</p>
                <p className="truncate text-[11px] text-slate-500">{artifact.task_id} · {artifact.evidence.length} checks · {formatRelative(artifact.created_at)}</p>
                {artifact.evidence.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {artifact.evidence.slice(0, 4).map((item, i) => evidenceChip(item, `${artifact.artifact_id}-${i}`))}
                  </div>
                )}
              </div>
              <span className={`self-center rounded-full px-2 py-0.5 text-[10px] ring-1 ${statusTone(artifact.status)}`}>{artifact.status}</span>
            </Link>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function MemoryCandidates({
  candidates,
  onPromote,
  onReject,
}: {
  candidates: ReturnType<typeof useMemoryCandidates>["candidates"];
  onPromote: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <Panel>
      {panelTitle("layers", "Memory Candidates", "View all")}
      <div className="space-y-2 p-4">
        {candidates.length === 0 && <EmptyState text="No memory candidates awaiting review." />}
        {candidates.slice(0, 4).map((candidate) => (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" key={candidate.memory_candidate_id}>
            <div className="flex items-center justify-between gap-3">
              <p className="truncate text-[12px] font-semibold text-slate-900">{candidate.memory_candidate_id}</p>
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-700">Needs Review</span>
            </div>
            <p className="mt-1 line-clamp-2 text-[12px] text-slate-600">{candidate.proposed_content}</p>
            <div className="mt-2 flex gap-2">
              <button className="rounded bg-blue-600 px-2 py-1 text-[11px] font-medium text-white" onClick={() => onPromote(candidate.memory_candidate_id)} type="button">Promote</button>
              <button className="rounded border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-600" onClick={() => onReject(candidate.memory_candidate_id)} type="button">Reject</button>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ProviderStatus({ providers }: { providers: Array<{ id: string; label: string; provider: string; model: string; status: string; healthy: boolean }> }) {
  return (
    <Panel>
      {panelTitle("workflow", "Provider Status")}
      <div className="grid grid-cols-2 gap-3 p-4 lg:grid-cols-4">
        {providers.length === 0 && <p className="col-span-full text-sm text-slate-400">No providers connected.</p>}
        {providers.slice(0, 8).map((provider) => (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-center" key={provider.id}>
            <div className="mx-auto grid size-10 place-items-center rounded-full bg-white text-blue-600 shadow-sm">
              <BrandIcon name="agent" size={18} />
            </div>
            <p className="mt-2 truncate text-[12px] font-semibold text-slate-900">{provider.label}</p>
            <p className="truncate text-[11px] text-slate-500">{provider.model}</p>
            <span className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-[10px] ring-1 ${statusTone(provider.status)}`}>{provider.status}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function RecentDiscussions({ messages }: { messages: Array<{ id: string; sender: string; content: string; timestamp: string }> }) {
  return (
    <Panel>
      {panelTitle("chat", "Recent Discussions", "View all")}
      <div className="space-y-2 p-4">
        {messages.length === 0 && <EmptyState text="No room discussion yet." />}
        {messages.slice(-4).reverse().map((message) => (
          <div className="flex gap-3 rounded-lg border border-slate-200 px-3 py-2" key={message.id}>
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-blue-100 text-[11px] font-bold text-blue-700">{message.sender.slice(0, 2).toUpperCase()}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12px] font-semibold text-slate-900">{message.sender}</p>
              <p className="truncate text-[12px] text-slate-500">{message.content}</p>
            </div>
            <span className="text-[11px] text-slate-400">{message.timestamp}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ProductAlphaCommandPanel({
  roomId,
  proposals,
  workers,
  commands,
  onCreate,
  onConfirm,
  onReject,
}: {
  roomId: string;
  proposals: CommandProposal[];
  workers: WorkerInfo[];
  commands: WorkerCommand[];
  onCreate: (body: { intent: string; provider: string; workspace_root: string }) => Promise<unknown>;
  onConfirm: (proposalId: string) => Promise<unknown>;
  onReject: (proposalId: string) => Promise<unknown>;
}) {
  const [intent, setIntent] = useState("");
  const [provider, setProvider] = useState("claude");
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setLocalError(null);
    try {
      await action();
      if (key === "create") setIntent("");
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Panel>
      {panelTitle("command", "Command Proposal Gate", "proposal -> confirm -> worker")}
      <div className="grid gap-4 p-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-3">
          <div>
            <label className="text-[11px] font-semibold uppercase text-slate-400" htmlFor="proposal-intent">Goal / command intent</label>
            <textarea
              className="mt-1 min-h-[92px] w-full resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 outline-none ring-blue-200 placeholder:text-slate-400 focus:ring-2"
              id="proposal-intent"
              onChange={(event) => setIntent(event.target.value)}
              placeholder="예: Wire onboarding invite flow to the NAT worker queue and produce a verified code_patch."
              value={intent}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-[150px_minmax(0,1fr)_auto]">
            <select
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none ring-blue-200 focus:ring-2"
              onChange={(event) => setProvider(event.target.value)}
              value={provider}
            >
              <option value="claude">Claude</option>
              <option value="codex">Codex</option>
              <option value="omo">OMO</option>
              <option value="hermes">Hermes</option>
            </select>
            <input
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none ring-blue-200 placeholder:text-slate-400 focus:ring-2"
              onChange={(event) => setWorkspaceRoot(event.target.value)}
              placeholder="Worker workspace root, optional"
              value={workspaceRoot}
            />
            <button
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
              disabled={!intent.trim() || busy === "create"}
              onClick={() => void run("create", () => onCreate({ intent: intent.trim(), provider, workspace_root: workspaceRoot.trim() }))}
              type="button"
            >
              Propose
            </button>
          </div>
          {localError && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{localError}</p>}
          <p className="text-[11px] text-slate-500">Room: <span className="font-mono">{roomId}</span>. Propose never enqueues. Confirm is the only execution boundary.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-1">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-[11px] font-semibold uppercase text-slate-400">Pending proposals</p>
            <p className="mt-1 text-2xl font-semibold text-slate-950">{proposals.length}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-[11px] font-semibold uppercase text-slate-400">Registered workers</p>
            <p className="mt-1 text-2xl font-semibold text-slate-950">{workers.length}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-[11px] font-semibold uppercase text-slate-400">Queued commands</p>
            <p className="mt-1 text-2xl font-semibold text-slate-950">{commands.filter((command) => command.state === "queued").length}</p>
          </div>
        </div>
      </div>
      <div className="border-t border-slate-200 p-4">
        {proposals.length === 0 ? (
          <p className="text-sm text-slate-400">No command proposals awaiting confirmation.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {proposals.slice(0, 6).map((proposal) => (
              <article className="rounded-lg border border-amber-200 bg-amber-50 p-3" key={proposal.proposal_id}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] font-semibold text-amber-800">{proposal.proposal_id}</span>
                  <span className="rounded-full bg-white px-2 py-0.5 text-[10px] text-amber-700 ring-1 ring-amber-200">{proposal.provider}</span>
                </div>
                <p className="mt-2 line-clamp-2 min-h-10 text-sm text-slate-800">{proposal.intent}</p>
                <p className="mt-2 truncate text-[11px] text-slate-500">{proposal.workspace_root || "No workspace root yet"}</p>
                <div className="mt-3 flex gap-2">
                  <button className="rounded bg-blue-600 px-2 py-1 text-[11px] font-medium text-white" onClick={() => void run(`confirm-${proposal.proposal_id}`, () => onConfirm(proposal.proposal_id))} type="button">Confirm</button>
                  <button className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-600" onClick={() => void run(`reject-${proposal.proposal_id}`, () => onReject(proposal.proposal_id))} type="button">Reject</button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function CommandBar({
  busy,
  inputRef,
  lastIntent,
  onOpenPalette,
  onPickNextAction,
  onSubmit,
  setValue,
  value,
}: {
  busy: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  lastIntent: { ok: boolean; message: string; nextActions: string[] } | null;
  onOpenPalette: () => void;
  onPickNextAction: (text: string) => void;
  onSubmit: () => void;
  setValue: (value: string) => void;
  value: string;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <input
          className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 outline-none ring-blue-200 placeholder:text-slate-400 focus:ring-2"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={'Tell Dipeen what to do — e.g. assign cap:claude "fix the login bug"   (⌘K for commands)'}
          ref={inputRef}
          value={value}
        />
        <button
          className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          disabled={busy || !value.trim()}
          onClick={onSubmit}
          type="button"
        >
          {busy ? "Running…" : "Run"}
        </button>
        <button
          className="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-500"
          onClick={onOpenPalette}
          title="Command palette"
          type="button"
        >
          ⌘K
        </button>
      </div>
      {lastIntent && (
        <div className={`mt-2 rounded-lg border px-3 py-2 text-sm ${lastIntent.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
          <p className="whitespace-pre-wrap font-medium">{lastIntent.message}</p>
          {lastIntent.nextActions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {lastIntent.nextActions.map((action, i) => (
                <button
                  className="rounded-md border border-slate-300 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-700"
                  key={i}
                  onClick={() => onPickNextAction(action)}
                  type="button"
                >
                  {action}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function ControlTower() {
  const { spec: workspaceSpec, loading: workspaceSpecLoading, error: workspaceSpecError, refetch: refetchWorkspaceSpec } = useWorkspaceSpec();
  const { summary, loading, error, refetch: refetchSummary } = useControlPlaneSummary();
  const { tasks, refetch: refetchTasks } = useTasks();
  const { currentProject, refetch: refetchProjects } = useProjects();
  const { usage, refetch: refetchUsage } = useUsage();
  const activeRoomId = currentProject?.room_id ?? "general";
  const { messages } = useChat(activeRoomId);
  const { permissions, approvePermission, rejectPermission, lastApprove, refetch: refetchPermissions } = usePermissions("requested");
  const { candidates, promoteCandidate, rejectCandidate, refetch: refetchMemoryCandidates } = useMemoryCandidates("pending");
  const {
    proposals,
    workers,
    commands,
    error: natError,
    refetch: refetchNat,
    createProposal,
    confirmProposal,
    rejectProposal,
  } = useNatProductAlpha(activeRoomId);
  const [activeFocus, setActiveFocus] = useState<FocusKey>("overview");
  const [refreshing, setRefreshing] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [intentText, setIntentText] = useState("");
  const [intentBusy, setIntentBusy] = useState(false);
  const [lastIntent, setLastIntent] = useState<{ ok: boolean; message: string; nextActions: string[] } | null>(null);
  const intentRef = useRef<HTMLInputElement>(null);
  const workspacePanelSet = useMemo(() => new Set(workspaceSpec?.ui.panels ?? []), [workspaceSpec?.ui.panels]);
  const hasWorkspacePanel = (panel: string) => {
    return workspacePanelSet.has(panel);
  };

  const progress = summary?.goal_progress ?? {
    total: tasks.length,
    done: tasks.filter((task) => taskBucket(task) === "DONE").length,
    running: tasks.filter((task) => taskBucket(task) === "RUNNING").length,
    ready: tasks.filter((task) => taskBucket(task) === "READY").length,
    waiting: 0,
    blocked: tasks.filter((task) => taskBucket(task) === "BLOCKED").length,
  };
  const latestEvents = summary?.latest_events ?? [];
  const latestArtifacts = summary?.latest_artifacts ?? [];
  const activeRuns = summary?.active_runs ?? [];
  const providerRows = summary?.providers ?? [];
  const healthRows = summary?.system_health ?? [];
  const pendingProposals = proposals.length ? proposals : summary?.pending_proposals ?? [];
  const workerRows = workers.length ? workers : summary?.workers ?? [];
  const commandRows = commands.length ? commands : summary?.queued_commands ?? [];
  const pendingPermissionRows = permissions.length ? permissions : summary?.pending_permissions ?? [];
  const memoryRows = candidates.length ? candidates : summary?.memory_candidates ?? [];
  const teamId = currentProject?.team_id ?? summary?.team_id ?? null;
  const projectName = currentProject?.name ?? workspaceSpec?.workspace_id ?? "Dipeen Team";

  const headerDetail = useMemo(() => {
    const projectLabel = projectName;
    const tokenText = usage.today_tokens ? `${usage.today_tokens.toLocaleString()} tokens today` : "No token usage today";
    return `${projectLabel} · ${tokenText}`;
  }, [projectName, usage.today_tokens]);

  const flowSignals = useMemo(
    () =>
      buildSignalsFromLiveState({
        hasWorkspace: Boolean(summary?.team_id || currentProject?.id),
        tasks,
        messages,
        proposals: pendingProposals,
        workers: workerRows,
        commands: commandRows,
        events: latestEvents,
        artifacts: latestArtifacts,
        permissions: pendingPermissionRows,
        memoryCandidates: memoryRows,
        goalProgress: { total: progress.total, done: progress.done, blocked: progress.blocked },
      }),
    [
      commandRows,
      currentProject?.id,
      latestArtifacts,
      latestEvents,
      memoryRows,
      messages,
      pendingPermissionRows,
      pendingProposals,
      progress.blocked,
      progress.done,
      progress.total,
      summary?.team_id,
      tasks,
      workerRows,
    ],
  );

  const flowCounts: ProductFlowCounts = {
    tasks: tasks.length,
    doneTasks: progress.done,
    workers: workerRows.length,
    proposals: pendingProposals.length,
    queuedCommands: commandRows.filter((command) => {
      const state = command.state.toLowerCase();
      return state.includes("queue") || state.includes("lease") || state.includes("run");
    }).length,
    runs: activeRuns.length,
    events: latestEvents.length,
    artifacts: latestArtifacts.length,
    permissions: pendingPermissionRows.length,
    memoryCandidates: memoryRows.length,
  };

  const focusCounts = useMemo<Record<FocusKey, number>>(
    () => ({
      overview: flowCounts.tasks + flowCounts.workers + flowCounts.artifacts + flowCounts.permissions,
      workers: flowCounts.workers + flowCounts.queuedCommands,
      routing: pendingProposals.length + tasks.filter((task) => task.assigned_agent_id || task.required_role).length,
      evidence: latestArtifacts.length,
      approvals: pendingPermissionRows.length,
    }),
    [
      flowCounts.artifacts,
      flowCounts.permissions,
      flowCounts.queuedCommands,
      flowCounts.tasks,
      flowCounts.workers,
      latestArtifacts.length,
      pendingPermissionRows.length,
      pendingProposals.length,
      tasks,
    ],
  );

  const refreshLiveState = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        refetchWorkspaceSpec(),
        refetchSummary(),
        refetchTasks(),
        refetchProjects(),
        refetchUsage(),
        refetchPermissions(),
        refetchMemoryCandidates(),
        refetchNat(),
      ]);
    } finally {
      setRefreshing(false);
    }
  };

  const submitIntent = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setIntentBusy(true);
    try {
      const result = await api.control.intent(trimmed, activeRoomId);
      const nextActions = Array.isArray(result.data?.next_actions) ? (result.data!.next_actions as string[]) : [];
      setLastIntent({ ok: result.ok, message: result.message, nextActions });
      if (result.ok) setIntentText("");
      await Promise.allSettled([refetchSummary(), refetchNat()]);
    } catch (e) {
      setLastIntent({ ok: false, message: e instanceof Error ? e.message : String(e), nextActions: [] });
    } finally {
      setIntentBusy(false);
    }
  }, [activeRoomId, refetchNat, refetchSummary]);

  const onPaletteSelect = useCallback((cmd: PaletteCommand) => {
    setPaletteOpen(false);
    if (cmd.needs_input) {
      setIntentText(cmd.template);
      window.setTimeout(() => intentRef.current?.focus(), 10);
    } else {
      void submitIntent(cmd.template);
    }
  }, [submitIntent]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      } else if (event.key === "Escape" && paletteOpen) {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen]);

  return (
    <div className="dp-app">
      <Sidebar roomId={activeRoomId} workspaceName={projectName} />
      <main className="dp-page-main overflow-auto">
        <header className="dp-topbar sticky top-0 z-10 flex items-center justify-between px-6">
          <div>
            <p className="text-[12px] font-semibold text-blue-700">Dipeen Control Tower</p>
            <h1 className="mt-1 text-xl font-semibold text-slate-950">Welcome back, {projectName}</h1>
            <p className="mt-1 text-xs text-slate-500">{headerDetail}</p>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-emerald-500" />Live</span>
            <span>{summary?.snapshot_at ? formatTime(summary.snapshot_at) : formatTime(new Date().toISOString())}</span>
            <Link className="rounded-lg border border-slate-200 px-3 py-2 font-medium text-slate-700" href="/settings">Settings</Link>
          </div>
        </header>

        <div className="space-y-4 p-5">
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              Control-plane API error: {error}
            </div>
          )}
          {loading && !summary && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
              Loading canonical control-plane state...
            </div>
          )}
          {natError && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              NAT command API error: {natError}
            </div>
          )}
          {workspaceSpecError && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              Workspace spec API error: {workspaceSpecError}
            </div>
          )}
          {workspaceSpecLoading && !workspaceSpec && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
              Loading TeamWorkspaceSpec from host CLI / HQ...
            </div>
          )}

          <CommandBar
            busy={intentBusy}
            inputRef={intentRef}
            lastIntent={lastIntent}
            onOpenPalette={() => setPaletteOpen(true)}
            onPickNextAction={(text) => {
              setIntentText(text);
              window.setTimeout(() => intentRef.current?.focus(), 10);
            }}
            onSubmit={() => void submitIntent(intentText)}
            setValue={setIntentText}
            value={intentText}
          />

          <ProductionSignalBar
            activeFocus={activeFocus}
            artifacts={latestArtifacts}
            commands={commandRows}
            onFocus={setActiveFocus}
            panelCount={workspaceSpec?.ui.panels.length}
            permissions={pendingPermissionRows}
            showDryRunBanner={workspaceSpec?.ui.show_dry_run_banner}
            tasks={tasks}
            workspaceId={workspaceSpec?.workspace_id}
            workspaceMode={workspaceSpec?.mode}
            workers={workerRows}
          />

          <FocusActionRail
            activeFocus={activeFocus}
            counts={focusCounts}
            onFocus={setActiveFocus}
            onRefresh={() => void refreshLiveState()}
            refreshing={refreshing}
          />

          {(hasWorkspacePanel("join_panel") || hasWorkspacePanel("demo_panel") || hasWorkspacePanel("worker_status") || hasWorkspacePanel("permission_inbox")) && (
            <div className="grid gap-4 xl:grid-cols-3">
              {hasWorkspacePanel("join_panel") && (
                <JoinInvitePanel
                  projectName={projectName}
                  roomId={activeRoomId}
                  teamId={teamId}
                  workers={workerRows}
                />
              )}
              {hasWorkspacePanel("demo_panel") && <DemoModePanel mode={workspaceSpec?.mode} />}
              {hasWorkspacePanel("worker_status") && <WorkerStatusPanel commands={commandRows} workers={workerRows} />}
              {hasWorkspacePanel("permission_inbox") && (
                <PermissionInbox
                  lastApprove={lastApprove}
                  permissions={pendingPermissionRows}
                  onApprove={(id) => void approvePermission(id)}
                  onReject={(id) => void rejectPermission(id)}
                />
              )}
            </div>
          )}

          {(hasWorkspacePanel("routing_preview") || hasWorkspacePanel("command_queue")) && (
            <div className="grid gap-4 xl:grid-cols-[0.82fr_1.18fr]">
              {hasWorkspacePanel("routing_preview") && <AssignmentRouting roomId={activeRoomId} />}
              {(hasWorkspacePanel("routing_preview") || hasWorkspacePanel("command_queue")) && (
                <ProductAlphaCommandPanel
                  commands={commandRows}
                  onConfirm={confirmProposal}
                  onCreate={createProposal}
                  onReject={rejectProposal}
                  proposals={pendingProposals}
                  roomId={activeRoomId}
                  workers={workerRows}
                />
              )}
            </div>
          )}

          {(hasWorkspacePanel("task_board") || hasWorkspacePanel("run_timeline") || hasWorkspacePanel("event_log") || hasWorkspacePanel("artifact_board")) && (
            <div className="grid gap-4 xl:grid-cols-[1.08fr_0.92fr_0.92fr]">
              {hasWorkspacePanel("task_board") && <TaskBoard tasks={tasks} />}
              {(hasWorkspacePanel("run_timeline") || hasWorkspacePanel("event_log")) && <RunTimeline events={latestEvents} />}
              {hasWorkspacePanel("artifact_board") && <LatestArtifacts artifacts={latestArtifacts} />}
            </div>
          )}

          {hasWorkspacePanel("permission_inbox") && <DecisionNudgePanel compact roomId={activeRoomId} variant="light" />}

          {(hasWorkspacePanel("goal_progress") || hasWorkspacePanel("system_health") || hasWorkspacePanel("active_runs")) && (
            <div className="grid gap-4 xl:grid-cols-[1.05fr_0.8fr_0.8fr]">
              {hasWorkspacePanel("goal_progress") && <GoalProgress {...progress} />}
              {hasWorkspacePanel("system_health") && <SystemHealth items={healthRows} />}
              {hasWorkspacePanel("active_runs") && <ActiveRuns runs={activeRuns} />}
            </div>
          )}

          {hasWorkspacePanel("meeting_room") && <ProductFlowSpine compact counts={flowCounts} signals={flowSignals} />}

          {(hasWorkspacePanel("memory_queue") || hasWorkspacePanel("provider_status") || hasWorkspacePanel("provider_inspect") || hasWorkspacePanel("recent_discussions") || hasWorkspacePanel("meeting_room")) && (
            <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr_1fr]">
              {hasWorkspacePanel("memory_queue") && (
                <MemoryCandidates
                  candidates={memoryRows}
                  onPromote={(id) => void promoteCandidate(id)}
                  onReject={(id) => void rejectCandidate(id)}
                />
              )}
              {(hasWorkspacePanel("provider_status") || hasWorkspacePanel("provider_inspect")) && <ProviderStatus providers={providerRows} />}
              {(hasWorkspacePanel("recent_discussions") || hasWorkspacePanel("meeting_room")) && <RecentDiscussions messages={messages} />}
            </div>
          )}
        </div>
      </main>
      <CommandPalette onClose={() => setPaletteOpen(false)} onSelect={onPaletteSelect} open={paletteOpen} />
    </div>
  );
}
