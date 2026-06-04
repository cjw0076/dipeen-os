"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { DipeenAppShell } from "@/components/layout/DipeenAppShell";
import { CommandPalette } from "@/components/command/CommandPalette";
import { MeetingWorkflowPanel } from "@/components/production/MeetingWorkflowPanel";
import { EvidenceDetailModal } from "@/components/production/EvidenceDetailModal";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import { useArtifacts } from "@/hooks/useArtifacts";
import { useControlPlaneSummary } from "@/hooks/useControlPlaneSummary";
import { useNatProductAlpha } from "@/hooks/useNatProductAlpha";
import { usePermissions } from "@/hooks/usePermissions";
import { useTasks } from "@/hooks/useTasks";
import { useWorkspaceSpec } from "@/hooks/useWorkspaceSpec";
import {
  api,
  type AssignmentSpec,
  type CommandProposal,
  type ControlPlaneArtifact,
  type ControlPlaneEvent,
  type PaletteCommand,
  type PermissionRequest,
  type RoutingPreview,
  type RoomMessage,
  type Task,
  type WorkerCommand,
  type WorkerInfo,
} from "@/lib/api";

type ToastTone = "ok" | "warn" | "danger";
type ToastState = { message: string; tone: ToastTone };
type TaskColumnKey = "ready" | "running" | "retry" | "permission" | "done";

const taskColumns: Array<{ key: TaskColumnKey; label: string }> = [
  { key: "ready", label: "Ready" },
  { key: "running", label: "Running" },
  { key: "retry", label: "Needs Retry" },
  { key: "permission", label: "Awaiting Permission" },
  { key: "done", label: "Done" },
];

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type EvidenceSource = "verified" | "reported" | "neutral";

// Distinguishes HQ-verified evidence from worker self-reported claims (Evidence First).
// VERIFIED: HQ independently confirmed (kinds containing "_verified", plus "git_diff_exists").
// REPORTED: worker self-claim, NOT independently verified ("_reported" suffix, legacy "tests_passed").
function evidenceSource(kind: string): EvidenceSource {
  if (kind.includes("_verified") || kind === "git_diff_exists") return "verified";
  if (kind.endsWith("_reported") || kind === "tests_passed") return "reported";
  return "neutral";
}

function readableEvidenceKind(kind: string): string {
  return kind.replace(/_verified$|_reported$/, "").replace(/_/g, " ").trim() || kind;
}

// Renders a single evidence chip that surfaces its provenance: blue = Verified by Dipeen,
// amber = Reported by worker (unverified), emerald/red = neutral OK/Fail. A failed check
// stays red regardless of source.
function evidenceChip(item: { kind: string; passed: boolean }, key: string) {
  const source = evidenceSource(item.kind);
  const label = readableEvidenceKind(item.kind);
  if (!item.passed) {
    return (
      <span
        className={cn("rounded-full border px-2 py-0.5 text-[11px] font-bold", "border-red-200 bg-red-50 text-red-700")}
        key={key}
        title={
          source === "verified"
            ? "Verified by Dipeen — check failed"
            : source === "reported"
              ? "Reported by worker — not independently verified — check failed"
              : "Check failed"
        }
      >
        {`Fail ${label}`}
      </span>
    );
  }
  if (source === "verified") {
    return (
      <span
        className={cn("rounded-full border px-2 py-0.5 text-[11px] font-bold", "border-indigo-200 bg-indigo-50 text-indigo-700")}
        key={key}
        title="Verified by Dipeen"
      >
        {`✓ Verified · ${label}`}
      </span>
    );
  }
  if (source === "reported") {
    return (
      <span
        className={cn("rounded-full border px-2 py-0.5 text-[11px] font-bold", "border-amber-200 bg-amber-50 text-amber-700")}
        key={key}
        title="Reported by worker — not independently verified"
      >
        {`⚑ Reported · ${label}`}
      </span>
    );
  }
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-bold", "border-emerald-200 bg-emerald-50 text-emerald-700")} key={key}>
      {`OK ${label}`}
    </span>
  );
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function formatRelative(value?: string | null) {
  if (!value) return "never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

function statusTone(status?: string | null) {
  const raw = (status ?? "").toLowerCase();
  if (raw.includes("done") || raw.includes("verified") || raw.includes("complete") || raw.includes("online")) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (raw.includes("run") || raw.includes("work") || raw.includes("lease") || raw.includes("progress")) {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  if (raw.includes("wait") || raw.includes("permission") || raw.includes("pending") || raw.includes("retry")) {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  if (raw.includes("fail") || raw.includes("block") || raw.includes("reject") || raw.includes("offline")) {
    return "border-red-200 bg-red-50 text-red-700";
  }
  return "border-slate-200 bg-slate-50 text-slate-600";
}

function chip(text: string, tone?: string) {
  return <span className={cn("rounded-md border px-2 py-0.5 text-[11px] font-bold", tone ?? "border-[var(--ds-border)] bg-[var(--ds-surface-raised)] text-[var(--ds-text-muted)]")}>{text}</span>;
}

function Panel({
  children,
  className,
  icon,
  right,
  title,
}: {
  children: ReactNode;
  className?: string;
  icon: BrandIconName;
  right?: ReactNode;
  title: string;
}) {
  return (
    <section className={cn("overflow-hidden rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] shadow-[var(--ds-shadow-card)]", className)}>
      <header className="flex min-h-11 items-center justify-between gap-3 border-b border-[var(--ds-border)] px-4">
        <div className="flex min-w-0 items-center gap-2">
          <BrandIcon className="text-[#b98545]" name={icon} size={16} />
          <h2 className="truncate text-sm font-bold text-[var(--ds-text)]">{title}</h2>
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-[var(--ds-border)] bg-[var(--ds-surface-warm)] px-4 py-5 text-sm leading-6 text-[var(--ds-text-muted)]">{children}</div>;
}

function parseCapability(capabilities: string[], prefix: string) {
  const found = capabilities.find((capability) => capability.startsWith(`${prefix}.`));
  return found ? found.slice(prefix.length + 1) : null;
}

function compactStrings(values: Array<string | null | undefined>) {
  return values.filter((value): value is string => Boolean(value?.trim()));
}

function collapseErrors(values: Array<string | null | undefined>) {
  const unique = Array.from(new Set(values.filter((value): value is string => Boolean(value)).map((value) => value.replace(/^Error:\s*/, ""))));
  if (unique.length === 0) return null;
  if (unique.length === 1) return unique[0];
  return `${unique[0]} (${unique.length} requests affected.)`;
}

function workspaceSlug(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "") || "dipeen-workspace";
}

function workerDisplay(worker: WorkerInfo) {
  const user = parseCapability(worker.capabilities, "user");
  const role = parseCapability(worker.capabilities, "role");
  const provider = parseCapability(worker.capabilities, "provider");
  const repo = parseCapability(worker.capabilities, "repo") ?? worker.workspaces?.[0]?.repo ?? worker.workspaces?.[0]?.workspace_ref?.replace("workspace://", "");
  return {
    label: user ? `${user} machine` : worker.worker_id,
    provider: provider ?? "provider not reported",
    repo: repo ?? "workspace not reported",
    role: role ?? "role not reported",
  };
}

function workerStatus(worker: WorkerInfo, commands: WorkerCommand[]) {
  const active = commands.find((command) => command.lease_owner === worker.worker_id && /lease|run|progress/i.test(command.state));
  if (active) return "working";
  if (/block|fail|error/i.test(worker.state)) return "blocked";
  const last = new Date(worker.last_heartbeat);
  if (Number.isNaN(last.getTime()) || Date.now() - last.getTime() > 5 * 60_000) return "offline";
  return "online";
}

function taskBucket(task: Task, permissions: PermissionRequest[]): TaskColumnKey {
  if (permissions.some((permission) => permission.task_id === task.task_id)) return "permission";
  const raw = task.status.toLowerCase();
  if (raw.includes("done") || raw.includes("complete")) return "done";
  if (raw.includes("retry") || raw.includes("fail") || raw.includes("block") || raw.includes("error")) return "retry";
  if (raw.includes("run") || raw.includes("progress") || raw.includes("work")) return "running";
  return "ready";
}

function artifactLabel(type: string) {
  return type.replaceAll("_", " ");
}

function humanRouting(preview: RoutingPreview | null, provider: string) {
  const worker = preview?.matching_workers.find((match) => match.online) ?? preview?.matching_workers[0];
  if (!worker) return preview?.reason || "Select a task or assignee to preview where work will run.";
  const target = worker.user ? `${worker.user} machine` : worker.worker_id;
  const via = provider ? `${provider[0]?.toUpperCase()}${provider.slice(1)}` : "selected provider";
  return `${target}에서 ${via}로 실행됩니다.`;
}

function safeModeText(policy?: string) {
  const mode = policy || "dry_run";
  if (mode === "local_execute") return "local_execute enabled";
  if (mode === "manual_handoff") return "manual handoff";
  return "dry_run · no PR / push / deploy by default";
}

function OverviewCard({ label, value, caption, tone = "neutral" }: { label: string; value: string | number; caption: string; tone?: "neutral" | "green" | "amber" | "blue" }) {
  const toneClass = {
    neutral: "text-[var(--ds-text)]",
    green: "text-emerald-700",
    amber: "text-amber-700",
    blue: "text-blue-700",
  }[tone];
  return (
    <article className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] px-4 py-3 shadow-[var(--ds-shadow-card)]">
      <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--ds-text-subtle)]">{label}</p>
      <p className={cn("mt-2 text-2xl font-bold tracking-tight", toneClass)}>{value}</p>
      <p className="mt-1 truncate text-xs text-[var(--ds-text-muted)]">{caption}</p>
    </article>
  );
}

function ArchitectureStrip({ hqStatus, onlineWorkers, policyMode }: { hqStatus: string; onlineWorkers: number; policyMode: string }) {
  return (
    <section className="grid gap-3 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-raised)] p-3 shadow-[var(--ds-shadow-card)] md:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0">
        <p className="text-sm font-bold text-[var(--ds-text)]">HQ coordinates. Local workers execute.</p>
        <p className="mt-1 text-xs leading-5 text-[var(--ds-text-muted)]">Commands are leased by `dipeen-agent`; Codex, Claude, and OMO credentials stay on teammate machines.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {chip(hqStatus, hqStatus.includes("error") ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700")}
        {chip(safeModeText(policyMode), "border-emerald-200 bg-emerald-50 text-emerald-800")}
        {chip(`${onlineWorkers} online`, "border-blue-200 bg-blue-50 text-blue-700")}
      </div>
    </section>
  );
}

export function ProductionControlRoom() {
  const { summary, loading: summaryLoading, error: summaryError, refetch: refetchSummary } = useControlPlaneSummary();
  const { spec: workspaceSpec, loading: specLoading, error: specError, refetch: refetchSpec } = useWorkspaceSpec();
  const { tasks, loading: tasksLoading, error: tasksError, refetch: refetchTasks, retryTask } = useTasks();
  const { artifacts, loading: artifactsLoading, error: artifactsError, refetch: refetchArtifacts } = useArtifacts();
  const { permissions, loading: permissionsLoading, error: permissionsError, approvePermission, rejectPermission, lastApprove, refetch: refetchPermissions } = usePermissions("requested");
  const { proposals, workers, commands, loading: natLoading, error: natError, refetch: refetchNat } = useNatProductAlpha("general");

  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState("");
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedRepo, setSelectedRepo] = useState("");
  const [selectedProvider, setSelectedProvider] = useState("");
  const [routingPreview, setRoutingPreview] = useState<RoutingPreview | null>(null);
  const [invite, setInvite] = useState<{ code: string; joinUrl: string; expiresAt: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [openArtifact, setOpenArtifact] = useState<ControlPlaneArtifact | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [intentText, setIntentText] = useState("");
  const [intentBusy, setIntentBusy] = useState(false);
  const [lastIntent, setLastIntent] = useState<{ ok: boolean; message: string; nextActions: string[] } | null>(null);
  const intentRef = useRef<HTMLInputElement>(null);

  const teamId = summary?.team_id ?? workspaceSpec?.workspace_id ?? null;
  const workspaceName = workspaceSpec?.workspace_id ?? summary?.team_id ?? "Dipeen workspace";
  const policyMode = workspaceSpec?.policies.permission_executor_mode ?? workspaceSpec?.policies["permission_executor_mode"] ?? "dry_run";
  const visibleWorkers = workers.length ? workers : summary?.workers ?? [];
  const visibleCommands = commands.length ? commands : summary?.queued_commands ?? [];
  const visibleArtifacts = artifacts.length ? artifacts : summary?.latest_artifacts ?? [];
  const visiblePermissions = permissions.length ? permissions : summary?.pending_permissions ?? [];
  const visibleProposals = proposals.length ? proposals : summary?.pending_proposals ?? [];
  const providerOptions = Array.from(new Set(compactStrings([
    ...Object.keys(workspaceSpec?.providers ?? {}),
    ...(summary?.providers.map((provider) => provider.provider) ?? []),
    ...visibleCommands.map((command) => command.provider),
    ...visibleWorkers.map((worker) => parseCapability(worker.capabilities, "provider")),
  ])));
  const roleOptions = Array.from(new Set(compactStrings([
    ...(workspaceSpec?.team.roles ?? []),
    ...tasks.map((task) => task.required_role),
    ...visibleWorkers.map((worker) => parseCapability(worker.capabilities, "role")),
  ])));
  const repoOptions = Array.from(new Set(compactStrings([
    ...(workspaceSpec?.project.repos.map((repo) => repo.id.replace(/^repo\./, "")) ?? []),
    ...visibleWorkers.flatMap((worker) => worker.workspaces?.map((workspace) => workspace.repo ?? workspace.workspace_ref.replace("workspace://", "")) ?? []),
  ])));

  const showToast = useCallback((message: string, tone: ToastTone = "ok") => {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 3200);
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.allSettled([refetchSummary(), refetchSpec(), refetchTasks(), refetchArtifacts(), refetchPermissions(), refetchNat()]);
  }, [refetchArtifacts, refetchNat, refetchPermissions, refetchSpec, refetchSummary, refetchTasks]);

  // Prompt box / palette → /api/control/intent. Reply is human-worded; next_actions are clickable.
  const submitIntent = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setIntentBusy(true);
    try {
      const result = await api.control.intent(trimmed, "general");
      const nextActions = Array.isArray(result.data?.next_actions) ? (result.data!.next_actions as string[]) : [];
      setLastIntent({ ok: result.ok, message: result.message, nextActions });
      showToast(result.message.split("\n")[0], result.ok ? "ok" : "warn");
      if (result.ok) setIntentText("");
      await refreshAll();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLastIntent({ ok: false, message, nextActions: [] });
      showToast(message, "danger");
    } finally {
      setIntentBusy(false);
    }
  }, [refreshAll, showToast]);

  const onPaletteSelect = useCallback((cmd: PaletteCommand) => {
    setPaletteOpen(false);
    if (cmd.needs_input) {
      setIntentText(cmd.template);
      window.setTimeout(() => intentRef.current?.focus(), 10);
    } else {
      void submitIntent(cmd.template);
    }
  }, [submitIntent]);

  // ⌘K / Ctrl+K toggles the palette anywhere; Esc closes it.
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

  useEffect(() => {
    if (!selectedRepo && repoOptions[0]) setSelectedRepo(repoOptions[0]);
  }, [repoOptions, selectedRepo]);

  useEffect(() => {
    if (roleOptions.length === 0) {
      if (selectedRole) setSelectedRole("");
      return;
    }
    if (!selectedRole || !roleOptions.includes(selectedRole)) setSelectedRole(roleOptions[0]);
  }, [roleOptions, selectedRole]);

  useEffect(() => {
    if (providerOptions.length === 0) {
      if (selectedProvider) setSelectedProvider("");
      return;
    }
    if (!selectedProvider || !providerOptions.includes(selectedProvider)) setSelectedProvider(providerOptions[0]);
  }, [providerOptions, selectedProvider]);

  const selectedTask = useMemo(
    () => tasks.find((task) => task.task_id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );

  const selectedTaskArtifacts = useMemo(
    () => visibleArtifacts.filter((artifact) => artifact.task_id === selectedTask?.task_id),
    [selectedTask?.task_id, visibleArtifacts],
  );

  const assignment: AssignmentSpec = useMemo(() => ({
    provider: selectedProvider,
    repo: selectedRepo || null,
    role: selectedRole || selectedTask?.required_role || null,
    user: selectedUser || null,
    workspace_ref: selectedRepo ? `workspace://${selectedRepo}` : null,
  }), [selectedProvider, selectedRepo, selectedRole, selectedTask?.required_role, selectedUser]);

  const previewRouting = useCallback(async (task?: Task | null) => {
    if (!selectedProvider) {
      showToast("No provider is reported by HQ yet.", "warn");
      return;
    }
    setBusy("routing");
    try {
      const preview = await api.routing.preview({
        ...assignment,
        role: assignment.role ?? task?.required_role ?? null,
      }, selectedProvider);
      setRoutingPreview(preview);
      showToast("Routing preview refreshed.");
    } catch (error) {
      showToast(error instanceof Error ? error.message : String(error), "danger");
    } finally {
      setBusy(null);
    }
  }, [assignment, selectedProvider, showToast]);

  const createInvite = useCallback(async () => {
    if (!teamId) {
      showToast("HQ team is not loaded yet.", "warn");
      return;
    }
    setBusy("invite");
    try {
      const result = await api.teams.invite(teamId);
      setInvite({ code: result.code, expiresAt: result.expires_at, joinUrl: result.join_url });
      showToast("Invite link created.");
    } catch (error) {
      showToast(error instanceof Error ? error.message : String(error), "danger");
    } finally {
      setBusy(null);
    }
  }, [showToast, teamId]);

  const joinUrl = invite?.joinUrl ?? null;
  const joinCommand = joinUrl && selectedRole
    ? `dipeen-agent join "${joinUrl}" --role ${selectedRole} --workspace ~/dipeen-workspaces/${workspaceSlug(workspaceName)} --start-worker`
    : null;

  const copyText = useCallback((value: string, label = "Copied") => {
    void navigator.clipboard?.writeText(value).then(() => showToast(label)).catch(() => showToast("Clipboard is not available.", "warn"));
  }, [showToast]);

  const runProposal = useCallback(async (proposal?: CommandProposal | null, task?: Task | null) => {
    if (!selectedProvider) {
      showToast("No provider is reported by HQ yet.", "warn");
      return;
    }
    setBusy("run");
    try {
      let proposalId = proposal?.proposal_id;
      if (!proposalId && task) {
        const created = await api.proposals.create({
          room_id: "general",
          proposed_by: "user://web",
          intent: task.prompt || task.subject,
          provider: selectedProvider,
          assignment: {
            ...assignment,
            role: assignment.role ?? task.required_role,
          },
          acceptance: [{ type: "artifact_required", artifact_type: "code_patch" }],
        });
        proposalId = created.proposal_id;
      }
      if (!proposalId) {
        showToast("No proposal or task selected.", "warn");
        return;
      }
      await api.proposals.confirm(proposalId);
      await refetchNat();
      await refetchSummary();
      showToast("Run command queued for a matching worker.");
    } catch (error) {
      showToast(error instanceof Error ? error.message : String(error), "danger");
    } finally {
      setBusy(null);
    }
  }, [assignment, refetchNat, refetchSummary, selectedProvider, showToast]);

  const groupedTasks = useMemo(() => {
    const initial: Record<TaskColumnKey, Task[]> = { ready: [], running: [], retry: [], permission: [], done: [] };
    for (const task of tasks) initial[taskBucket(task, visiblePermissions)].push(task);
    return initial;
  }, [tasks, visiblePermissions]);

  const errorMessage = collapseErrors([summaryError, specError, tasksError, artifactsError, permissionsError, natError]);
  const loading = summaryLoading || specLoading || tasksLoading || artifactsLoading || permissionsLoading || natLoading;
  const onlineWorkers = visibleWorkers.filter((worker) => workerStatus(worker, visibleCommands) !== "offline").length;
  const runningTasks = tasks.filter((task) => taskBucket(task, visiblePermissions) === "running").length;
  const evidenceCount = visibleArtifacts.length;
  const hqStatus = summaryError ? "HQ API error" : summary ? "HQ API connected" : "HQ API loading";

  return (
    <DipeenAppShell
      activeLabels={["Overview"]}
      eyebrow="Dipeen Production Control Room"
      footerCaption="single-page control room"
      right={(
        <>
          <span className={cn(
            "inline-flex min-h-9 items-center gap-2 rounded-lg border bg-[var(--ds-surface)] px-3 text-xs font-bold shadow-sm",
            summaryError ? "border-amber-200 text-amber-700" : "border-emerald-200 text-emerald-700",
          )}>
            <span className={cn("size-2 rounded-full", summaryError ? "bg-amber-500" : "bg-emerald-500")} />
            {hqStatus}
          </span>
          {chip(safeModeText(policyMode), "border-emerald-200 bg-emerald-50 text-emerald-800")}
          {chip(`${onlineWorkers} workers`, "border-blue-200 bg-blue-50 text-blue-700")}
          <button className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] px-3 py-2 text-xs font-bold text-[var(--ds-text)] shadow-sm" onClick={() => void refreshAll()} type="button">
            Refresh
          </button>
        </>
      )}
      subtitle={`${workspaceSpec?.mode ?? "production"} · ${workspaceName} · ${summary?.snapshot_at ? formatTime(summary.snapshot_at) : "live state"}`}
      title="Dipeen HQ Control Room"
      visibleNavLabels={["Overview"]}
      workspaceName={workspaceName}
    >
      <div className="space-y-4 bg-[var(--ds-bg)] p-4 lg:p-5">
        <ArchitectureStrip hqStatus={hqStatus} onlineWorkers={onlineWorkers} policyMode={policyMode} />

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <OverviewCard caption={`${visibleWorkers.length} registered`} label="Workers" tone="green" value={`${onlineWorkers}/${visibleWorkers.length || 0}`} />
          <OverviewCard caption="leased or running" label="Running" tone="blue" value={runningTasks} />
          <OverviewCard caption="worker submissions" label="Evidence" value={evidenceCount} />
          <OverviewCard caption="approval required" label="Permissions" tone={visiblePermissions.length ? "amber" : "neutral"} value={visiblePermissions.length} />
        </section>

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

        {loading && <span className="sr-only">Loading production control-plane state...</span>}
        {errorMessage && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
            {errorMessage}
          </div>
        )}

        <div className="grid min-w-0 gap-4 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-4">
            <JoinPanel
              busy={busy}
              invite={invite}
              joinCommand={joinCommand}
              joinUrl={joinUrl}
              onCopy={copyText}
              onInvite={createInvite}
              selectedRole={selectedRole}
              setSelectedRole={setSelectedRole}
              teamId={teamId}
              roleOptions={roleOptions}
              workspaceName={workspaceName}
            />
            <WorkerList commands={visibleCommands} workers={visibleWorkers} />
          </div>

          <div className="min-w-0 space-y-4">
            <MeetingWorkflowPanel
              assignment={assignment}
              onLoopAdvanced={refreshAll}
              onToast={showToast}
              provider={selectedProvider}
            />
            <TaskBoard
              artifacts={visibleArtifacts}
              busy={busy}
              groupedTasks={groupedTasks}
              onOpenEvidence={(task) => {
                setSelectedTaskId(task.task_id);
                const first = visibleArtifacts.find((a) => a.task_id === task.task_id);
                if (first) setOpenArtifact(first);
              }}
              onPreview={(task) => {
                setSelectedTaskId(task.task_id);
                void previewRouting(task);
              }}
              onRetry={(task) => void retryTask(task.task_id).then(() => showToast("Task moved back to Ready.")).catch((error) => showToast(error instanceof Error ? error.message : String(error), "danger"))}
              onRun={(task) => void runProposal(null, task)}
              permissions={visiblePermissions}
              selectedTaskId={selectedTask?.task_id ?? null}
            />
            <details className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] shadow-[var(--ds-shadow-card)]">
              <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-[var(--ds-text)]">Routing controls</summary>
              <RoutingPreviewPanel
                assignment={assignment}
                busy={busy}
                onPreview={() => void previewRouting(selectedTask)}
                preview={routingPreview}
                provider={selectedProvider}
                repoOptions={repoOptions}
                roleOptions={roleOptions}
                selectedProvider={selectedProvider}
                selectedRepo={selectedRepo}
                selectedRole={selectedRole}
                selectedTask={selectedTask}
                selectedUser={selectedUser}
                setSelectedProvider={setSelectedProvider}
                setSelectedRepo={setSelectedRepo}
                setSelectedRole={setSelectedRole}
                setSelectedUser={setSelectedUser}
                userOptions={visibleWorkers}
                providerOptions={providerOptions}
              />
            </details>
          </div>

          <div className="min-w-0 space-y-4">
            <EvidenceBoard artifacts={selectedTaskArtifacts.length ? selectedTaskArtifacts : visibleArtifacts} onOpen={setOpenArtifact} selectedTask={selectedTask} />
            <PermissionInbox
              lastApprove={lastApprove}
              onApprove={(permission) => void approvePermission(permission.permission_request_id).then(() => showToast("Approved in dry-run mode.")).catch((error) => showToast(error instanceof Error ? error.message : String(error), "danger"))}
              onHandoff={(permission) => copyText(`Manual handoff: ${permission.action} ${permission.target ?? ""}\\nReason: ${permission.reason}`, "Manual handoff copied")}
              onReject={(permission) => void rejectPermission(permission.permission_request_id).then(() => showToast("Permission rejected.")).catch((error) => showToast(error instanceof Error ? error.message : String(error), "danger"))}
              permissions={visiblePermissions}
            />
            <ProposalQueue busy={busy} onRun={(proposal) => void runProposal(proposal)} proposals={visibleProposals} />
            <TimelinePanel events={summary?.latest_events ?? []} />
          </div>
        </div>
      </div>
      <CommandPalette onClose={() => setPaletteOpen(false)} onSelect={onPaletteSelect} open={paletteOpen} />
      {toast && (
        <div className={cn(
          "fixed bottom-5 right-5 z-50 rounded-lg border px-4 py-3 text-sm font-bold shadow-[var(--ds-shadow-floating)]",
          toast.tone === "danger" ? "border-red-200 bg-red-50 text-red-700" : toast.tone === "warn" ? "border-amber-200 bg-amber-50 text-amber-800" : "border-emerald-200 bg-emerald-50 text-emerald-800",
        )}>
          {toast.message}
        </div>
      )}
      {openArtifact && <EvidenceDetailModal artifact={openArtifact} onClose={() => setOpenArtifact(null)} />}
    </DipeenAppShell>
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
    <section className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] p-3 shadow-[var(--ds-shadow-card)]">
      <div className="flex items-center gap-2">
        <input
          className="min-w-0 flex-1 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] px-3 py-2 text-sm text-[var(--ds-text)] outline-none placeholder:text-[var(--ds-text-muted)]"
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
          className="shrink-0 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] px-3 py-2 text-xs font-bold text-[var(--ds-text)] shadow-sm disabled:opacity-50"
          disabled={busy || !value.trim()}
          onClick={onSubmit}
          type="button"
        >
          {busy ? "Running…" : "Run"}
        </button>
        <button
          className="shrink-0 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] px-3 py-2 text-xs font-bold text-[var(--ds-text-muted)] shadow-sm"
          onClick={onOpenPalette}
          title="Command palette"
          type="button"
        >
          ⌘K
        </button>
      </div>
      {lastIntent && (
        <div
          className={cn(
            "mt-2 rounded-md border px-3 py-2 text-sm",
            lastIntent.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800",
          )}
        >
          <p className="whitespace-pre-wrap font-semibold">{lastIntent.message}</p>
          {lastIntent.nextActions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {lastIntent.nextActions.map((action, i) => (
                <button
                  className="rounded-md border border-[var(--ds-border)] bg-[var(--ds-surface)] px-2 py-0.5 text-[11px] font-bold text-[var(--ds-text)]"
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

function TimelinePanel({ events }: { events: ControlPlaneEvent[] }) {
  const sorted = [...events]
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
    .slice(0, 30);
  return (
    <Panel icon="workflow" right={chip(`${events.length} events`)} title="Timeline">
      <div className="max-h-[360px] space-y-2 overflow-y-auto p-3">
        {sorted.length === 0 ? (
          <EmptyState>No events yet. Actions appear here as work flows through Dipeen.</EmptyState>
        ) : (
          sorted.map((event) => (
            <div className="flex gap-3 text-sm" key={event.event_id}>
              <span className="shrink-0 pt-0.5 text-[11px] font-bold tabular-nums text-[var(--ds-text-muted)]">
                {formatTime(event.created_at)}
              </span>
              <div className="min-w-0">
                <span className={cn("rounded-md border px-1.5 py-0.5 text-[10px] font-bold", statusTone(event.event_type))}>
                  {event.event_type.replace(/_/g, " ")}
                </span>
                <p className="mt-0.5 truncate text-[var(--ds-text)]" title={event.message}>
                  {event.message || event.producer}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}

function JoinPanel({
  busy,
  invite,
  joinCommand,
  joinUrl,
  onCopy,
  onInvite,
  roleOptions,
  selectedRole,
  setSelectedRole,
  teamId,
  workspaceName,
}: {
  busy: string | null;
  invite: { code: string; joinUrl: string; expiresAt: string } | null;
  joinCommand: string | null;
  joinUrl: string | null;
  onCopy: (value: string, label?: string) => void;
  onInvite: () => void;
  roleOptions: string[];
  selectedRole: string;
  setSelectedRole: (role: string) => void;
  teamId: string | null;
  workspaceName: string;
}) {
  const canCreateInvite = Boolean(teamId);
  const canCopyCommand = Boolean(joinCommand);

  return (
    <Panel icon="key" right={chip(teamId ?? "team loading")} title="Join Panel">
      <div className="space-y-3 p-4">
        <div className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] p-3">
          <p className="text-sm font-bold text-[var(--ds-text)]">{workspaceName}</p>
          <p className="mt-1 text-xs leading-5 text-[var(--ds-text-muted)]">Teammates join from their own machine. BYOK stays local.</p>
          <label className="mt-3 block text-[11px] font-bold uppercase text-[#9a6a35]" htmlFor="join-role">Worker role</label>
          <select
            className="mt-1 h-9 w-full rounded-lg border border-[var(--ds-border)] bg-white px-2 text-sm font-semibold text-[var(--ds-text)] disabled:opacity-60"
            disabled={roleOptions.length === 0}
            id="join-role"
            onChange={(event) => setSelectedRole(event.target.value)}
            value={selectedRole}
          >
            {roleOptions.length === 0 && <option value="">No roles reported</option>}
            {roleOptions.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
        </div>

        {joinCommand ? (
          <code className="block break-all rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] px-3 py-3 text-[12px] leading-5 text-[var(--ds-text)]">{joinCommand}</code>
        ) : (
          <EmptyState>
            {invite
              ? "Invite exists, but no worker role is available in TeamWorkspaceSpec or worker capability state yet."
              : "No active invite. Create one to generate the one-touch join command."}
          </EmptyState>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            className={cn(
              "rounded-lg px-3 py-2 text-xs font-bold shadow-sm disabled:cursor-not-allowed",
              canCopyCommand ? "bg-[#b98545] text-white" : "border border-[var(--ds-border)] bg-[var(--ds-bg-muted)] text-[var(--ds-text-subtle)]",
            )}
            disabled={!canCopyCommand}
            onClick={() => joinCommand && onCopy(joinCommand, "Join command copied")}
            type="button"
          >
            Copy command
          </button>
          <button
            className={cn(
              "rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold shadow-sm disabled:cursor-not-allowed",
              canCreateInvite ? "bg-white text-[var(--ds-text)]" : "bg-[var(--ds-bg-muted)] text-[var(--ds-text-subtle)]",
            )}
            disabled={busy === "invite" || !canCreateInvite}
            onClick={onInvite}
            type="button"
          >
            {busy === "invite" ? "Creating..." : "Create invite"}
          </button>
          {joinUrl && (
            <button className="rounded-lg border border-[var(--ds-border)] bg-white px-3 py-2 text-xs font-bold text-[var(--ds-text)] shadow-sm" onClick={() => onCopy(joinUrl, "Join URL copied")} type="button">
              Copy URL
            </button>
          )}
        </div>
        {invite ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
            Invite <span className="font-mono font-bold">{invite.code}</span> expires {formatTime(invite.expiresAt)}
          </div>
        ) : (
          <p className="text-xs text-[var(--ds-text-subtle)]">Invite creation calls the HQ API.</p>
        )}
      </div>
    </Panel>
  );
}

function WorkerList({ commands, workers }: { commands: WorkerCommand[]; workers: WorkerInfo[] }) {
  return (
    <Panel icon="agent" right={<span className="text-xs font-bold text-slate-500">{workers.length} registered</span>} title="Worker Status">
      <div className="space-y-3 p-4">
        {workers.length === 0 && <EmptyState>No workers connected. Run the join command on a teammate machine to see it here.</EmptyState>}
        {workers.slice(0, 4).map((worker) => {
          const display = workerDisplay(worker);
          const active = commands.find((command) => command.lease_owner === worker.worker_id && /lease|run|progress/i.test(command.state));
          const status = workerStatus(worker, commands);
          return (
            <article className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] p-3" key={worker.worker_id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-[var(--ds-text)]">{display.label}</p>
                  <p className="mt-1 text-xs text-[var(--ds-text-muted)]">role: {display.role} · provider: {display.provider}</p>
                </div>
                {chip(status, statusTone(status))}
              </div>
              <p className="mt-2 truncate text-xs text-[var(--ds-text-muted)]">workspace: {display.repo}</p>
              <p className="mt-1 text-[11px] text-[var(--ds-text-subtle)]">heartbeat {formatRelative(worker.last_heartbeat)}</p>
              {active && (
                <div className="mt-3 rounded-lg border border-[#dcc3a0] bg-[var(--ds-surface-raised)] px-3 py-2 text-xs text-[#8b5b22]">
                  <p className="font-bold">{active.command_type} · {active.state}</p>
                  <p className="mt-1 truncate">task {active.task_id} · run {active.run_id}</p>
                </div>
              )}
            </article>
          );
        })}
        {workers.length > 4 && <p className="px-1 text-xs text-[var(--ds-text-subtle)]">+ {workers.length - 4} more workers registered</p>}
      </div>
    </Panel>
  );
}

function RoutingPreviewPanel({
  busy,
  onPreview,
  preview,
  provider,
  providerOptions,
  repoOptions,
  roleOptions,
  selectedProvider,
  selectedRepo,
  selectedRole,
  selectedTask,
  selectedUser,
  setSelectedProvider,
  setSelectedRepo,
  setSelectedRole,
  setSelectedUser,
  userOptions,
}: {
  assignment: AssignmentSpec;
  busy: string | null;
  onPreview: () => void;
  preview: RoutingPreview | null;
  provider: string;
  providerOptions: string[];
  repoOptions: string[];
  roleOptions: string[];
  selectedProvider: string;
  selectedRepo: string;
  selectedRole: string;
  selectedTask: Task | null;
  selectedUser: string;
  setSelectedProvider: (value: string) => void;
  setSelectedRepo: (value: string) => void;
  setSelectedRole: (value: string) => void;
  setSelectedUser: (value: string) => void;
  userOptions: WorkerInfo[];
}) {
  return (
    <Panel icon="workflow" right={chip(preview?.deliverable ? "deliverable" : "preview", preview?.deliverable ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600")} title="Routing Preview">
      <div className="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_260px]">
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
          <p className="text-sm font-bold text-blue-950">{humanRouting(preview, provider)}</p>
          <p className="mt-1 text-xs leading-5 text-blue-700">
            {selectedTask ? `Selected task: ${selectedTask.subject}` : "Select a task card or preview a new assignment."}
          </p>
          {preview?.matching_workers[0] && (
            <div className="mt-3 grid gap-2 text-xs text-[var(--ds-text-muted)]">
              <span>Matched role: {(preview.matching_workers[0].role ?? selectedRole) || "any"}</span>
              <span>Matched person: {(preview.matching_workers[0].user ?? selectedUser) || "any available teammate"}</span>
              <span>Matched repo: {(preview.matching_workers[0].repo ?? selectedRepo) || "workspace default"}</span>
            </div>
          )}
        </div>
        <div className="grid gap-2">
          <select className="h-9 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-raised)] px-2 text-sm font-semibold text-[var(--ds-text)]" onChange={(event) => setSelectedRole(event.target.value)} value={selectedRole}>
            {roleOptions.length === 0 && <option value="">No roles reported</option>}
            {roleOptions.map((role) => <option key={role} value={role}>{role}</option>)}
          </select>
          <select className="h-9 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-raised)] px-2 text-sm font-semibold text-[var(--ds-text)]" onChange={(event) => setSelectedUser(event.target.value)} value={selectedUser}>
            <option value="">Any teammate</option>
            {userOptions.map((worker) => {
              const display = workerDisplay(worker);
              const user = parseCapability(worker.capabilities, "user") ?? worker.worker_id;
              return <option key={worker.worker_id} value={user}>{display.label}</option>;
            })}
          </select>
          <select className="h-9 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-raised)] px-2 text-sm font-semibold text-[var(--ds-text)]" onChange={(event) => setSelectedRepo(event.target.value)} value={selectedRepo}>
            <option value="">Workspace default</option>
            {repoOptions.map((repo) => <option key={repo} value={repo}>{repo}</option>)}
          </select>
          <select className="h-9 rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-raised)] px-2 text-sm font-semibold text-[var(--ds-text)]" onChange={(event) => setSelectedProvider(event.target.value)} value={selectedProvider}>
            {providerOptions.length === 0 && <option value="">No providers reported</option>}
            {providerOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <button className="rounded-lg bg-[#b98545] px-3 py-2 text-xs font-bold text-white shadow-sm disabled:opacity-60" disabled={busy === "routing"} onClick={onPreview} type="button">
            Preview assignment
          </button>
        </div>
      </div>
    </Panel>
  );
}

function TaskBoard({
  artifacts,
  busy,
  groupedTasks,
  onOpenEvidence,
  onPreview,
  onRetry,
  onRun,
  permissions,
  selectedTaskId,
}: {
  artifacts: ControlPlaneArtifact[];
  busy: string | null;
  groupedTasks: Record<TaskColumnKey, Task[]>;
  onOpenEvidence: (task: Task) => void;
  onPreview: (task: Task) => void;
  onRetry: (task: Task) => void;
  onRun: (task: Task) => void;
  permissions: PermissionRequest[];
  selectedTaskId: string | null;
}) {
  return (
    <Panel icon="board" right={<span className="text-xs font-bold text-slate-500">Ready to Done</span>} title="Task Board">
      <div className="grid gap-3 overflow-x-auto p-4 xl:grid-cols-5">
        {taskColumns.map((column) => (
          <div className="min-w-[190px] rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] p-2" key={column.key}>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-bold leading-4 text-slate-700">
                {column.label === "Awaiting Permission" ? <>Awaiting<br />Permission</> : column.label}
              </p>
              {chip(String(groupedTasks[column.key].length))}
            </div>
            <div className="space-y-2">
              {groupedTasks[column.key].length === 0 && <p className="px-2 py-5 text-xs text-[var(--ds-text-subtle)]">Empty</p>}
              {groupedTasks[column.key].slice(0, 3).map((task) => {
                const taskArtifacts = artifacts.filter((artifact) => artifact.task_id === task.task_id);
                const taskPermission = permissions.find((permission) => permission.task_id === task.task_id);
                return (
                  <article className={cn("rounded-lg border bg-white p-3 shadow-sm", selectedTaskId === task.task_id ? "border-[#b98545] ring-2 ring-[#ead5b7]" : "border-[var(--ds-border)]")} key={task.task_id}>
                    <p className="line-clamp-2 text-sm font-bold text-slate-950">{task.subject}</p>
                    <p className="mt-1 font-mono text-[11px] text-slate-400">{task.task_id}</p>
                    <dl className="mt-2 space-y-1 text-[11px] text-slate-500">
                      <div className="flex justify-between gap-2"><dt>담당</dt><dd className="truncate">{task.assigned_agent_id ?? task.required_role ?? "unassigned"}</dd></div>
                      <div className="flex justify-between gap-2"><dt>State</dt><dd>{taskPermission ? "Awaiting permission" : task.status}</dd></div>
                      <div className="flex justify-between gap-2"><dt>Artifacts</dt><dd>{taskArtifacts.length}</dd></div>
                    </dl>
                    <div className="mt-3 grid grid-cols-2 gap-1.5">
                      <button className="rounded border border-[var(--ds-border)] bg-white px-2 py-1.5 text-[11px] font-bold text-[var(--ds-text)]" onClick={() => onPreview(task)} type="button">Assign</button>
                      <button className="rounded border border-[#d6b98e] bg-[var(--ds-surface-warm)] px-2 py-1.5 text-[11px] font-bold text-[#8b5b22] disabled:opacity-60" disabled={busy === "run"} onClick={() => onRun(task)} type="button">Run</button>
                      <button className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] font-bold text-amber-700" onClick={() => onRetry(task)} type="button">Retry</button>
                      <button className="rounded border border-slate-200 bg-white px-2 py-1.5 text-[11px] font-bold text-slate-700" onClick={() => onOpenEvidence(task)} type="button">Evidence</button>
                    </div>
                  </article>
                );
              })}
              {groupedTasks[column.key].length > 3 && <p className="px-2 pt-1 text-[11px] text-[var(--ds-text-subtle)]">+ {groupedTasks[column.key].length - 3} more</p>}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function EvidenceBoard({ artifacts, onOpen, selectedTask }: { artifacts: ControlPlaneArtifact[]; onOpen: (a: ControlPlaneArtifact) => void; selectedTask: Task | null }) {
  return (
    <Panel icon="database" right={chip(`${artifacts.length} artifacts`)} title="Evidence Board">
      <div className="space-y-3 p-4">
        {selectedTask && <p className="text-xs text-slate-500">Showing evidence for <span className="font-bold text-slate-700">{selectedTask.subject}</span> when available.</p>}
        {artifacts.length === 0 && <EmptyState>No evidence yet. When a worker submits code_patch, test_report, or command_receipt, it appears here.</EmptyState>}
        {artifacts.slice(0, 5).map((artifact) => (
          <article className="cursor-pointer rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] p-3 hover:border-[#b98545]" key={artifact.artifact_id} onClick={() => onOpen(artifact)}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-bold text-slate-950">{artifact.title || artifactLabel(artifact.type)}</p>
                <p className="mt-1 text-xs text-slate-500">{artifact.summary}</p>
              </div>
              {chip(artifact.status, statusTone(artifact.status))}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {artifact.evidence.slice(0, 3).map((item, index) => evidenceChip(item, `${artifact.artifact_id}-${item.kind}-${index}`))}
            </div>
          </article>
        ))}
        {artifacts.length > 5 && <p className="px-1 text-xs text-[var(--ds-text-subtle)]">+ {artifacts.length - 5} more evidence items</p>}
      </div>
    </Panel>
  );
}

function PermissionInbox({
  lastApprove,
  onApprove,
  onHandoff,
  onReject,
  permissions,
}: {
  lastApprove: { executor_mode: string; command_id: string | null; message: string } | null;
  onApprove: (permission: PermissionRequest) => void;
  onHandoff: (permission: PermissionRequest) => void;
  onReject: (permission: PermissionRequest) => void;
  permissions: PermissionRequest[];
}) {
  return (
    <Panel icon="shield" right={chip(`${permissions.length} pending`, permissions.length ? "border-amber-200 bg-amber-50 text-amber-700" : undefined)} title="Permission Inbox">
      <div className="space-y-3 p-4">
        {lastApprove && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
            Last approval: {lastApprove.executor_mode} {lastApprove.command_id ? `· ${lastApprove.command_id}` : ""} · {lastApprove.message}
          </div>
        )}
        {permissions.length === 0 && <EmptyState>No risky action is waiting for human approval.</EmptyState>}
        {permissions.map((permission) => (
          <article className="rounded-lg border border-amber-200 bg-amber-50 p-3" key={permission.permission_request_id}>
            <p className="text-sm font-bold text-slate-950">{permission.action}</p>
            <p className="mt-1 text-xs text-slate-600">Requester: {permission.requester}</p>
            <p className="mt-1 text-xs text-slate-600">Mode: dry_run · Target: {permission.target ?? "not specified"}</p>
            <p className="mt-2 text-xs leading-5 text-slate-700">{permission.reason}</p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <button className="rounded-lg bg-[#b98545] px-2 py-2 text-[11px] font-bold text-white shadow-sm" onClick={() => onApprove(permission)} type="button">Approve dry-run</button>
              <button className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-[11px] font-bold text-slate-700 shadow-sm" onClick={() => onReject(permission)} type="button">Reject</button>
              <button className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-[11px] font-bold text-slate-700 shadow-sm" onClick={() => onHandoff(permission)} type="button">Manual handoff</button>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}

function ProposalQueue({ busy, onRun, proposals }: { busy: string | null; onRun: (proposal: CommandProposal) => void; proposals: CommandProposal[] }) {
  return (
    <Panel icon="play" right={chip(`${proposals.length} ready`)} title="Task Proposals">
      <div className="space-y-2 p-4">
        {proposals.length === 0 && <EmptyState>No pending proposal. Use Meeting Room to create one.</EmptyState>}
        {proposals.slice(0, 2).map((proposal) => (
          <article className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] p-3" key={proposal.proposal_id}>
            <p className="line-clamp-2 text-sm font-bold text-slate-950">{proposal.intent}</p>
            <p className="mt-1 text-xs text-slate-500">Provider: {proposal.provider} · State: {proposal.state}</p>
            <button className="mt-3 rounded-lg bg-[#b98545] px-3 py-2 text-xs font-bold text-white shadow-sm disabled:opacity-60" disabled={busy === "run"} onClick={() => onRun(proposal)} type="button">
              Run
            </button>
          </article>
        ))}
        {proposals.length > 2 && <p className="px-1 text-xs text-[var(--ds-text-subtle)]">+ {proposals.length - 2} more proposals</p>}
      </div>
    </Panel>
  );
}
