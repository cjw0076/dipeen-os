"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { useAgentActivity, type ActivityItem } from "@/hooks/useAgentActivity";
import { useAgents, type LiveAgent } from "@/hooks/useAgents";
import { useArtifacts } from "@/hooks/useArtifacts";
import { useChat, type ChatMessage } from "@/hooks/useChat";
import { useControlPlaneSummary } from "@/hooks/useControlPlaneSummary";
import { useMeeting, type MeetingMode, type MeetingPhase } from "@/hooks/useMeeting";
import { useProjects } from "@/hooks/useProjects";
import { useTasks } from "@/hooks/useTasks";
import { useUsage, type UsageSummary } from "@/hooks/useUsage";
import { useUserProfile } from "@/hooks/useUserProfile";
import { useHermes } from "@/hooks/useHermes";
import { auth } from "@/lib/auth";
import { api, getApiBaseUrl, type Task as ApiTask } from "@/lib/api";
import { Office3DScene } from "@/components/office/Office3DScene";
import { ProjectGraph } from "@/components/graph/ProjectGraph";
import { LogStream } from "@/components/workbench/LogStream";
import { DecisionNudgePanel } from "@/components/decisions/DecisionNudgePanel";
import { dipeenNavItems, resolveDipeenNavHref } from "@/components/layout/dipeen-nav";
import { SpatialOfficeCanvasFrame } from "@/components/spatial";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";

type AgentRole = "PM" | "FE" | "BE" | "QA";
type PersonRole = AgentRole | "Human";
type Tone = "blue" | "green" | "purple" | "yellow" | "red" | "slate";

type Agent = {
  id: string;
  name: string;
  role: AgentRole;
  title: string;
  status: "Online" | "Running" | "Idle" | "Away";
  tasks: number;
  done: number;
  success: number;
  tokens: string;
  location: string;
};

type Task = {
  id: string;
  title: string;
  status: "To Do" | "In Progress" | "Review" | "Done";
  role: AgentRole;
  points: number;
  branch?: string;
  pr?: string;
  delta?: string;
  tag?: string;
};

type Message = {
  author: string;
  role: AgentRole | "Human";
  time: string;
  body: string;
  meta?: string;
};

const roleTitles: Record<AgentRole, string> = {
  PM: "Planning and Specs",
  FE: "Frontend Engineer",
  BE: "Backend Engineer",
  QA: "Quality Assurance",
};

const defaultLocations: Record<AgentRole, string> = {
  PM: "Meeting Room",
  FE: "Desk 4A",
  BE: "Desk 2B",
  QA: "QA Station",
};

function normalizeRole(value?: string | null, fallback: AgentRole = "FE"): AgentRole {
  const raw = (value ?? "").toLowerCase();
  if (raw.includes("pm") || raw.includes("product") || raw.includes("planning")) return "PM";
  if (raw.includes("be") || raw.includes("back") || raw.includes("server") || raw.includes("api")) return "BE";
  if (raw.includes("qa") || raw.includes("quality") || raw.includes("test")) return "QA";
  if (raw.includes("fe") || raw.includes("front") || raw.includes("ui") || raw.includes("web")) return "FE";
  return fallback;
}

function normalizePersonRole(value?: string | null): PersonRole {
  const raw = (value ?? "").toLowerCase();
  if (raw.includes("human") || raw.includes("user") || raw.includes("alex") || raw === "you") return "Human";
  return normalizeRole(value);
}

function normalizeAgentStatus(value?: string | null): Agent["status"] {
  const raw = (value ?? "").toLowerCase();
  if (raw.includes("run") || raw.includes("work") || raw.includes("progress") || raw.includes("execut")) return "Running";
  if (raw.includes("idle") || raw.includes("pending") || raw.includes("ready")) return "Idle";
  if (raw.includes("away") || raw.includes("offline") || raw.includes("disconnect") || raw.includes("error")) return "Away";
  return "Online";
}

function normalizeTaskStatus(value?: string | null): Task["status"] {
  const raw = (value ?? "").toLowerCase();
  if (raw.includes("done") || raw.includes("complete") || raw.includes("merge")) return "Done";
  if (raw.includes("review")) return "Review";
  if (raw.includes("progress") || raw.includes("run") || raw.includes("work") || raw.includes("execute")) return "In Progress";
  if (raw.includes("block") || raw.includes("fail") || raw.includes("error") || raw.includes("cancel")) return "Review";
  return "To Do";
}

function estimatePoints(task: ApiTask): number {
  const complexity = (task.complexity ?? "").toLowerCase();
  if (complexity.includes("high") || complexity.includes("large")) return 5;
  if (complexity.includes("low") || complexity.includes("small")) return 2;
  return 3;
}

function formatTokens(value?: number | null): string {
  const tokens = value ?? 0;
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens >= 10_000_000 ? 0 : 2)}M`;
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`;
  return String(tokens);
}

function taskFromApi(task: ApiTask): Task {
  const role = normalizeRole(task.required_role ?? task.assigned_agent_id ?? undefined, "FE");
  const status = normalizeTaskStatus(task.status);
  const prLabel = task.pr_url?.match(/\/pull\/(\d+)/)?.[1];
  return {
    id: task.task_id || task.id,
    title: task.subject || "Untitled task",
    status,
    role,
    points: estimatePoints(task),
    branch: task.branch ?? undefined,
    pr: prLabel ? `PR #${prLabel}` : task.pr_url ? "PR" : undefined,
    delta: status === "Done" ? "Merged" : task.pr_url ? "Open" : undefined,
    tag: task.required_skills?.[0] ?? task.complexity ?? undefined,
  };
}

function agentStatsFor(role: AgentRole, apiTasks: ApiTask[]) {
  const roleTasks = apiTasks.filter((task) => {
    const roleSource = task.required_role ?? task.assigned_agent_id;
    return roleSource ? normalizeRole(roleSource) === role : false;
  });
  const completed = roleTasks.filter((task) => normalizeTaskStatus(task.status) === "Done").length;
  return {
    tasks: roleTasks.length,
    done: completed,
    success: roleTasks.length ? Math.round((completed / roleTasks.length) * 100) : 0,
  };
}

// 라이브 전용: 실제 등록된 에이전트만 매핑한다(목업 PM/FE/BE/QA 패딩 제거).
// 빈 배열이면 UI가 "에이전트 없음" 빈 상태를 보여준다.
function agentsFromApi(liveAgents: LiveAgent[], apiTasks: ApiTask[], usageByAgent: Record<string, number>): Agent[] {
  return liveAgents.map((liveAgent) => {
    const role = normalizeRole(liveAgent.role ?? liveAgent.agent_id);
    const stats = agentStatsFor(role, apiTasks);
    const tokenCount = usageByAgent[liveAgent.agent_id] ?? liveAgent.tokens_used_this_month;
    return {
      id: liveAgent.agent_id,
      name: liveAgent.label || liveAgent.agent_id,
      role,
      title: roleTitles[role],
      status: normalizeAgentStatus(liveAgent.status),
      tasks: stats.tasks,
      done: stats.done,
      success: stats.success,
      tokens: tokenCount ? formatTokens(tokenCount) : "0",
      location: defaultLocations[role],
    };
  });
}

function messageFromChat(message: ChatMessage): Message {
  const role = normalizePersonRole(message.role ?? message.sender_type ?? message.sender);
  const meta = [
    message.task_id ? `Task ${message.task_id}` : "",
    typeof message.metadata_json?.kind === "string" ? String(message.metadata_json.kind) : "",
  ].filter(Boolean).join(" | ");
  return {
    author: message.sender,
    role,
    time: message.timestamp,
    body: message.content || message.text || "",
    meta: meta || undefined,
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function stringArray(value: unknown): string[] {
  return asArray(value)
    .map((item) => {
      if (typeof item === "string") return item.trim();
      const record = asRecord(item);
      return stringValue(record?.text) ?? stringValue(record?.title) ?? stringValue(record?.name);
    })
    .filter((item): item is string => Boolean(item));
}

function taskResult(task?: ApiTask): Record<string, unknown> {
  return asRecord(task?.result) ?? {};
}

function taskArtifacts(task?: ApiTask): Record<string, unknown> {
  return asRecord(taskResult(task).artifacts) ?? {};
}

type ChangedFileRow = { file: string; state: string };

function changedFilesFromUnknown(value: unknown): ChangedFileRow[] {
  return asArray(value).flatMap((item) => {
    if (typeof item === "string" && item.trim()) return [{ file: item.trim(), state: "M" }];
    const record = asRecord(item);
    if (!record) return [];
    const file = stringValue(record.file) ?? stringValue(record.path) ?? stringValue(record.name);
    if (!file) return [];
    return [{ file, state: stringValue(record.state) ?? stringValue(record.status) ?? "M" }];
  });
}

function changedFilesForTask(task?: ApiTask, activities: ActivityItem[] = []): ChangedFileRow[] {
  const fromTask = changedFilesFromUnknown(taskArtifacts(task).changed_files)
    .concat(changedFilesFromUnknown(taskResult(task).changed_files));
  if (fromTask.length) return fromTask;
  return activities.flatMap((activity) =>
    changedFilesFromUnknown(activity.metadata.changed_files).concat(changedFilesFromUnknown(activity.metadata.files))
  );
}

type ExecutionRow = { time: string; level: "INFO" | "WARN" | "ERROR"; text: string };

function executionRowsForTask(task?: ApiTask, activities: ActivityItem[] = []): ExecutionRow[] {
  const rows = activities.map((activity) => {
    const levelRaw = (stringValue(activity.metadata.level) ?? activity.kind).toLowerCase();
    const level: ExecutionRow["level"] = levelRaw.includes("error")
      ? "ERROR"
      : levelRaw.includes("warn") || levelRaw.includes("block")
        ? "WARN"
        : "INFO";
    return {
      time: activity.timestamp,
      level,
      text: activity.text || stringValue(activity.metadata.text) || activity.kind,
    };
  });
  if (rows.length) return rows;
  if (!task) return [];
  return [
    { time: new Date(task.created_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }), level: "INFO", text: `Task created: ${task.subject}` },
    { time: new Date(task.updated_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }), level: normalizeTaskStatus(task.status) === "Review" ? "WARN" : "INFO", text: `Current status: ${task.status}` },
  ];
}

function testSummaryForTask(task?: ApiTask, activities: ActivityItem[] = []) {
  const candidates = [taskResult(task).tests, taskArtifacts(task).tests, ...activities.map((activity) => activity.metadata.tests)];
  for (const candidate of candidates) {
    const record = asRecord(candidate);
    if (!record) continue;
    const passed = Number(record.passed ?? record.pass ?? 0);
    const failed = Number(record.failed ?? record.fail ?? 0);
    const running = Number(record.running ?? 0);
    const total = Number(record.total ?? passed + failed + running);
    if (total > 0) {
      const percent = Math.round((passed / total) * 100);
      return { passed, failed, running, total, percent };
    }
  }
  return null;
}

function checklistForTask(task?: ApiTask, activities: ActivityItem[] = []) {
  if (!task) return [];
  return [
    { label: "Task created", done: true, detail: task.task_id },
    { label: "Agent assigned", done: Boolean(task.assigned_agent_id), detail: task.assigned_agent_id ?? "waiting" },
    { label: "Branch prepared", done: Boolean(task.branch), detail: task.branch ?? "not reported" },
    { label: "Execution activity", done: activities.length > 0, detail: activities.length ? `${activities.length} events` : "no stream yet" },
    { label: "Pull request", done: Boolean(task.pr_url), detail: task.pr_url ? "available" : "not created" },
    { label: "Completed result", done: normalizeTaskStatus(task.status) === "Done", detail: task.status },
  ];
}

function blockersForTask(tasks: ApiTask[], activities: ActivityItem[] = []) {
  const taskBlockers = tasks
    .filter((task) => ["blocked", "error", "cancelled"].some((status) => task.status.toLowerCase().includes(status)) || task.blocked_by)
    .map((task) => ({
      id: task.task_id,
      tone: task.status.toLowerCase().includes("error") ? "red" : "yellow",
      title: task.subject,
      body: task.blocked_by ? `Blocked by ${task.blocked_by}` : task.status,
    }));
  const activityBlockers = activities
    .filter((activity) => ["question", "blocker", "error"].some((kind) => activity.kind.toLowerCase().includes(kind)))
    .map((activity) => ({
      id: activity.id,
      tone: activity.kind.toLowerCase().includes("error") ? "red" : "yellow",
      title: activity.kind,
      body: activity.text,
    }));
  return [...activityBlockers, ...taskBlockers].slice(0, 4);
}

function usagePercent(tokens: number, cap: number) {
  return Math.max(1, Math.min(100, Math.round((tokens / cap) * 100)));
}

const roleStyles: Record<PersonRole, { bg: string; text: string; ring: string; tone: Tone }> = {
  PM: { bg: "bg-agent-pm", text: "text-black", ring: "ring-agent-pm/40", tone: "yellow" },
  FE: { bg: "bg-agent-fe", text: "text-white", ring: "ring-agent-fe/40", tone: "blue" },
  BE: { bg: "bg-agent-be", text: "text-black", ring: "ring-agent-be/40", tone: "green" },
  QA: { bg: "bg-agent-qa", text: "text-white", ring: "ring-agent-qa/40", tone: "purple" },
  Human: { bg: "bg-blue-600", text: "text-white", ring: "ring-blue-500/40", tone: "blue" },
};

const agentArt: Record<PersonRole, { src: string; alt: string; color: string }> = {
  PM: { src: "/assets/agents/pm-agent.png", alt: "PM Agent character", color: "#fbbf24" },
  FE: { src: "/assets/agents/fe-agent.png", alt: "FE Agent character", color: "#3b82f6" },
  BE: { src: "/assets/agents/be-agent.png", alt: "BE Agent character", color: "#34d399" },
  QA: { src: "/assets/agents/qa-agent.png", alt: "QA Agent character", color: "#8b5cf6" },
  Human: { src: "/assets/agents/human-manager.png", alt: "Human manager character", color: "#60a5fa" },
};

const toneClass: Record<Tone, string> = {
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  green: "border-emerald-200 bg-emerald-50 text-emerald-700",
  purple: "border-violet-200 bg-violet-50 text-violet-700",
  yellow: "border-amber-200 bg-amber-50 text-amber-700",
  red: "border-red-200 bg-red-50 text-red-700",
  slate: "border-slate-200 bg-slate-50 text-slate-700",
};

const navItems = dipeenNavItems;

function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`dp-panel ${className}`}>
      {children}
    </section>
  );
}

function DipeenMark({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="flex items-center gap-3" href="/">
      <div className="grid size-9 place-items-center rounded-[7px] bg-gradient-to-br from-[#684cff] to-[#3568ff] text-lg font-black text-white shadow-[0_0_24px_rgba(88,95,255,0.35)]">
        D
      </div>
      {!compact && <span className="text-2xl font-semibold tracking-[-0.01em] text-white">Dipeen</span>}
    </Link>
  );
}

function RoleBadge({ role, className = "" }: { role: PersonRole; className?: string }) {
  const style = roleStyles[role];
  return (
    <span className={`inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold ${style.bg} ${style.text} ${className}`}>
      {role === "Human" ? "H" : role}
    </span>
  );
}

function AgentPortrait({
  role,
  mode = "head",
  size = "md",
  className = "",
}: {
  role: PersonRole;
  mode?: "head" | "full" | "office";
  size?: "xs" | "sm" | "md" | "lg" | "xl" | "hero";
  className?: string;
}) {
  const asset = agentArt[role];
  const sizeClass = {
    xs: "size-8",
    sm: "size-10",
    md: "size-12",
    lg: "size-16",
    xl: "size-20",
    hero: "size-24",
  }[size];

  return (
    <span
      className={`agent-portrait agent-portrait--${mode} ${sizeClass} ${className}`}
      style={{ "--agent-role-color": asset.color } as CSSProperties}
    >
      <img alt={asset.alt} draggable={false} src={asset.src} />
    </span>
  );
}

function StatusDot({ status = "Online" }: { status?: string }) {
  const color = status === "Away" ? "bg-amber-400" : status === "Idle" ? "bg-zinc-500" : "bg-emerald-400";
  return <span className={`inline-block size-2 rounded-full ${color}`} />;
}

function IconButton({
  icon,
  label,
  href,
  onClick,
}: {
  icon: BrandIconName;
  label: string;
  href?: string;
  onClick?: () => void;
}) {
  const cls = "dp-control grid size-10 place-items-center rounded-lg";
  if (href) {
    return (
      <Link aria-label={label} className={cls} href={href} title={label}>
        <BrandIcon name={icon} size={18} />
      </Link>
    );
  }
  return (
    <button aria-label={label} className={cls} onClick={onClick} title={label} type="button">
      <BrandIcon name={icon} size={18} />
    </button>
  );
}

function SideNav({ active, agents: navAgents = [], roomId }: { active: string; agents?: Agent[]; roomId?: string }) {
  const { name, emoji } = useUserProfile();
  return (
    <aside className="dp-sidebar hidden flex-col xl:flex">
      <DipeenMark />
      <nav className="mt-9 space-y-1">
        {navItems.map((item) => {
          const selected = item.label === active;
          const href = resolveDipeenNavHref(item, roomId);
          return (
            <Link
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                selected ? "dp-active" : "text-zinc-400 hover:bg-white/[0.04] hover:text-white"
              }`}
              href={href}
              key={item.label}
            >
              <BrandIcon name={item.icon} size={18} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="mt-8 border-t border-white/10 pt-6">
        <p className="mb-3 px-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500">Team AI Agents</p>
        <div className="space-y-2">
          {navAgents.length === 0 && (
            <p className="px-3 py-2 text-xs leading-5 text-zinc-500">No connected agents yet.</p>
          )}
          {navAgents.map((agent, index) => (
            <div className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-zinc-300" key={`${agent.id}-${index}`}>
              <AgentPortrait mode="head" role={agent.role} size="xs" />
              <span className="flex-1">{agent.name}</span>
              <StatusDot status={agent.status} />
            </div>
          ))}
        </div>
      </div>
      <Link
        className="mt-auto block rounded-xl border border-white/10 bg-white/[0.035] p-3 transition hover:bg-white/[0.06]"
        href="/settings"
      >
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-full bg-gradient-to-br from-blue-500 to-violet-500 text-lg">{emoji}</div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">{name}</p>
            <p className="text-xs text-zinc-500">프로필 · 설정</p>
          </div>
        </div>
      </Link>
    </aside>
  );
}

function TopBar({ title, detail, onInvite }: { title: string; detail?: ReactNode; onInvite?: () => void }) {
  return (
    <header className="dp-topbar flex items-center justify-between px-4 lg:px-6">
      <div className="flex items-center gap-4">
        <div className="xl:hidden">
          <DipeenMark compact />
        </div>
        <div className="hidden h-8 w-px bg-slate-200 xl:block" />
        <div>
          <p className="text-sm font-semibold text-slate-950">{title}</p>
          {detail && <div className="mt-1 text-xs text-zinc-500">{detail}</div>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button className="dp-control hidden rounded-lg px-3 py-2 text-sm md:inline-flex" onClick={onInvite} type="button">
          Invite
        </button>
        <IconButton href="/app" icon="command" label="Control Room" />
        <IconButton href="/settings" icon="settings" label="Settings" />
        <Link aria-label="Settings" href="/settings" title="My profile">
          <AgentPortrait mode="head" role="Human" size="sm" />
        </Link>
      </div>
    </header>
  );
}

function TaskCard({ task }: { task: Task }) {
  const isDone = task.status === "Done";
  return (
    <article className="rounded-lg border border-white/10 bg-[#111419] p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-medium leading-5 text-zinc-100">{task.title}</h4>
        <RoleBadge className="size-6 rounded-md text-[10px]" role={task.role} />
      </div>
      <div className="mt-3 flex items-center gap-3 text-xs text-zinc-500">
        <span>{task.id}</span>
        <span>{task.points} pts</span>
      </div>
      {task.branch && (
        <div className="mt-3 border-t border-white/10 pt-3 text-xs">
          <p className="mb-2 flex items-center gap-2 text-zinc-400">
            <BrandIcon name="branch" size={14} />
            {task.branch}
          </p>
          <div className="flex items-center gap-2">
            <span className="text-zinc-400">{task.pr}</span>
            <span className="rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-emerald-300">Open</span>
            <span className="ml-auto text-emerald-300">{task.delta}</span>
          </div>
        </div>
      )}
      {isDone && (
        <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-3 text-xs">
          <span className="text-zinc-400">{task.pr}</span>
          <span className="text-violet-300">{task.delta}</span>
        </div>
      )}
      {task.tag && <span className="mt-3 inline-flex rounded bg-white/[0.06] px-2 py-1 text-xs text-zinc-400">{task.tag}</span>}
    </article>
  );
}

function BoardColumns({ items = [], onAddTask }: { items?: Task[]; onAddTask?: () => void }) {
  const statuses: Task["status"][] = ["To Do", "In Progress", "Review", "Done"];
  return (
    <div className="grid h-full min-h-0 gap-3 xl:grid-cols-4">
      {statuses.map((status) => {
        const columnItems = items.filter((task) => task.status === status);
        return (
          <Panel className="flex min-h-[420px] flex-col rounded-xl" key={status}>
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white">{status}</h3>
                <span className="rounded-md bg-white/[0.08] px-1.5 py-0.5 text-xs text-zinc-400">{columnItems.length}</span>
              </div>
              <button className="text-xl leading-none text-zinc-500 hover:text-white" onClick={onAddTask} type="button">+</button>
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
              {columnItems.map((task) => <TaskCard key={task.id} task={task} />)}
            </div>
            <button className="m-3 mt-0 flex items-center gap-2 rounded-lg px-2 py-2 text-sm text-zinc-300 hover:bg-white/[0.04]" onClick={onAddTask} type="button">
              <span className="text-xl leading-none">+</span>
              Add task
            </button>
          </Panel>
        );
      })}
    </div>
  );
}

function ChatStream({ rows }: { rows: Message[] }) {
  return (
    <div className="space-y-0">
      {rows.map((message, index) => (
        <div className="flex gap-4 border-b border-white/10 px-4 py-5" key={`${message.author}-${index}`}>
          <AgentPortrait mode="head" role={message.role} size="md" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-white">{message.author}</span>
              {message.role !== "Human" && <span className="rounded border border-white/10 bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-zinc-300">BOT</span>}
              <span className="text-xs text-zinc-500">{message.time}</span>
            </div>
            <p className="mt-1 text-sm leading-6 text-zinc-200">{message.body}</p>
            {message.meta && (
              <div className="mt-3 inline-flex max-w-full items-center gap-2 rounded-md border border-white/10 bg-[#0b0d12] px-3 py-2 text-xs text-zinc-400">
                <BrandIcon name="branch" size={14} />
                <span className="truncate">{message.meta}</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function Composer({
  placeholder = "Message workspace",
  onSend,
}: {
  placeholder?: string;
  onSend?: (text: string) => Promise<void> | void;
}) {
  const [value, setValue] = useState("");
  const [sending, setSending] = useState(false);

  const submit = async () => {
    const text = value.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await onSend?.(text);
      setValue("");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="m-4 rounded-xl border border-white/10 bg-white/[0.04] p-3">
      <textarea
        className="h-14 w-full resize-none bg-transparent text-sm text-white outline-none placeholder:text-zinc-500"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            void submit();
          }
        }}
        placeholder={placeholder}
        value={value}
      />
      <div className="mt-2 flex items-center justify-between">
        <div className="flex gap-2 text-zinc-500">
          <IconButton icon="code" label="Code" />
          <IconButton icon="chat" label="Mention" />
        </div>
        <button
          className="grid size-10 place-items-center rounded-lg bg-gradient-to-br from-[#4f6cff] to-[#7657ff] text-white shadow-[0_0_28px_rgba(94,92,255,0.35)] disabled:opacity-50"
          disabled={!value.trim() || sending}
          onClick={() => void submit()}
          type="button"
        >
          <BrandIcon name="play" size={17} />
        </button>
      </div>
    </div>
  );
}

export function ProductionProjectGraph() {
  const { agents: apiAgents } = useAgents();
  const { tasks: apiTasks } = useTasks();
  const { usage } = useUsage();
  const { currentProject } = useProjects();
  const { summary } = useControlPlaneSummary();
  const liveAgents = useMemo(
    () => agentsFromApi(apiAgents, apiTasks, usage.by_agent),
    [apiAgents, apiTasks, usage.by_agent]
  );
  const roomId = currentProject?.room_id ?? "general";

  return (
    <div className="dp-app">
      <SideNav active="Project Graph" agents={liveAgents} roomId={roomId} />
      <main className="dp-page-main">
        <TopBar
          detail={
            <span className="text-xs text-zinc-500">
              {currentProject?.name ?? "프로젝트"} · 영속 조직 그래프 (드래그·연결로 편집)
            </span>
          }
          title="Project Graph"
        />
        <div className="min-h-0 flex-1 p-3">
          <div className="mb-3 grid gap-3 md:grid-cols-4">
            {[
              ["Runs", summary?.active_runs.length ?? 0],
              ["Artifacts", summary?.latest_artifacts.length ?? 0],
              ["Permissions", summary?.pending_permissions.length ?? 0],
              ["Memory", summary?.memory_candidates.length ?? 0],
            ].map(([label, value]) => (
              <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-[0_10px_34px_rgba(15,23,42,0.06)]" key={label}>
                <p className="text-[11px] font-semibold uppercase text-slate-400">{label}</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
              </div>
            ))}
          </div>
          <ProjectGraph projectId={currentProject?.id} />
        </div>
      </main>
    </div>
  );
}

export function ProductionCommandCenter({ roomId, roomName }: { roomId?: string; roomName?: string } = {}) {
  const { agents: apiAgents } = useAgents();
  const { tasks: apiTasks, createTask } = useTasks();
  const { currentProject } = useProjects();
  const activeRoomId = roomId ?? currentProject?.room_id ?? "general";
  const activeRoomName = roomName ?? currentProject?.name ?? "Team Workspace";
  const { messages: chatMessages, sendMessage } = useChat(activeRoomId);
  const { usage } = useUsage();

  // 라이브 전용(목업 fallback 제거) — 비어 있으면 빈 상태를 보여준다.
  const liveAgents = useMemo(() => agentsFromApi(apiAgents, apiTasks, usage.by_agent), [apiAgents, apiTasks, usage.by_agent]);
  const liveTasks = useMemo(() => apiTasks.map(taskFromApi), [apiTasks]);
  const roomMessages = useMemo(() => chatMessages.map(messageFromChat), [chatMessages]);
  const todayTokens = usage.today_tokens || 0;
  const tokenCap = 2_000_000;
  const tokenUsedPercent = usagePercent(todayTokens, tokenCap);
  const doneTasks = liveTasks.filter((task) => task.status === "Done").length;
  const progressPercent = liveTasks.length ? Math.round((doneTasks / liveTasks.length) * 100) : 0;
  const activeBranch = apiTasks.find((task) => task.branch)?.branch ?? currentProject?.default_branch ?? "main";

  const handleAddTask = async () => {
    const subject = typeof window !== "undefined" ? window.prompt("새 태스크 제목") : null;
    if (subject?.trim()) await createTask(subject.trim(), subject.trim());
  };

  // 초대: 실제 invite 코드 발급 → 합류 링크를 클립보드에 복사("모두 초대"의 핵심)
  const handleInvite = async () => {
    try {
      const me = await api.auth.me();
      const teamId = me.team_id || "default-team";
      const inv = await api.teams.invite(teamId);
      const link = `${window.location.origin}/onboarding?code=${inv.code}`;
      try { await navigator.clipboard?.writeText(link); } catch { /* clipboard 차단 가능 */ }
      window.alert(`초대 링크가 클립보드에 복사됐습니다:\n${link}\n\n코드: ${inv.code}`);
    } catch (e) {
      window.alert("초대 생성 실패: " + String(e));
    }
  };

  return (
    <div className="dp-app">
      <SideNav active="Overview" agents={liveAgents} roomId={activeRoomId} />
      <main className="dp-page-main">
        <TopBar
          detail={
            <span className="inline-flex items-center gap-2">
              <StatusDot />
              {liveAgents.length + 1} humans and agents in this room
            </span>
          }
          onInvite={handleInvite}
          title={activeRoomName}
        />
        <div className="border-b border-slate-200 bg-white px-4 py-3 lg:px-6">
          <DecisionNudgePanel compact roomId={activeRoomId} variant="light" />
        </div>
        <div className="grid gap-0 border-b border-slate-200 bg-white px-4 py-3 lg:grid-cols-[1fr_auto_280px] lg:px-6">
          <div className="flex min-w-0 items-center gap-3 overflow-x-auto">
            {liveAgents.length === 0 && (
              <span className="text-sm text-slate-500">에이전트가 아직 없습니다 — 팀을 초대해 노드를 연결하세요.</span>
            )}
            {liveAgents.map((agent, index) => (
              <button className="flex min-w-[155px] items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left transition hover:border-blue-200 hover:bg-blue-50" key={`${agent.id}-${index}`} type="button">
                <AgentPortrait mode="head" role={agent.role} size="sm" />
                <span>
                  <span className="block text-sm font-medium text-slate-950">{agent.name}</span>
                  <span className="flex items-center gap-2 text-xs text-slate-500"><StatusDot status={agent.status} /> {agent.status}</span>
                </span>
              </button>
            ))}
          </div>
          <div className="hidden min-w-[270px] border-x border-white/10 px-6 lg:block">
            <div className="flex items-end justify-between text-sm">
              <span className="text-zinc-400">Tokens Today</span>
              <span className="text-zinc-300">{tokenUsedPercent}%</span>
            </div>
            <p className="mt-1 text-xl font-semibold text-white">{formatTokens(todayTokens)} <span className="text-sm font-normal text-zinc-500">/ {formatTokens(tokenCap)}</span></p>
            <div className="mt-3 h-1.5 rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: `${tokenUsedPercent}%` }} /></div>
          </div>
          <div className="hidden rounded-lg border border-white/10 bg-white/[0.035] px-4 py-2 lg:block">
            <div className="flex items-center gap-2 text-sm font-semibold text-white"><BrandIcon name="branch" size={16} /> {activeRoomName}</div>
            <div className="mt-2 flex items-center justify-between text-sm text-zinc-400">
              <span>{activeBranch}</span>
              <span className="text-emerald-300">{currentProject?.status ?? "live"}</span>
            </div>
          </div>
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[42%_58%]">
          <Panel className="flex min-h-0 flex-col border-y-0 border-l-0">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-white"># {activeRoomId}</h2>
                <span className="rounded-md border border-accent/25 bg-accent/10 px-2 py-1 text-xs text-blue-200">Live</span>
              </div>
              <div className="flex gap-2 text-zinc-400">
                <BrandIcon name="inspect" size={18} />
                <BrandIcon name="settings" size={18} />
              </div>
            </div>
            <div className="border-b border-white/10 px-5 py-3 text-sm text-zinc-400">
              <span className="text-zinc-200">AI Workspace</span>
              <span className="mx-3 text-zinc-700">|</span>
              All agents and humans in this room
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {roomMessages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-sm text-zinc-500">
                  <BrandIcon name="chat" size={28} />
                  <p>아직 메시지가 없습니다.</p>
                  <p className="text-xs">아래에 메시지를 보내 회의를 시작하면 PM-Agent가 응답합니다.</p>
                </div>
              ) : (
                <ChatStream rows={roomMessages} />
              )}
            </div>
            <Composer onSend={sendMessage} placeholder={`Message ${activeRoomName}`} />
          </Panel>
          <section className="flex min-h-0 flex-col border-l border-white/10 bg-[#080a0f]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
              <div className="flex gap-5">
                {["Board", "Backlog", "Roadmap", "Reports"].map((tab, index) => (
                  <button className={`border-b-2 px-1 py-2 text-sm ${index === 0 ? "border-accent text-white" : "border-transparent text-zinc-400"}`} key={tab} type="button">{tab}</button>
                ))}
              </div>
              <div className="flex gap-2">
                <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-zinc-300" type="button">Filters</button>
                <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-zinc-300" type="button">Group: Status</button>
              </div>
            </div>
            <div className="min-h-0 flex-1 p-3">
              <BoardColumns items={liveTasks} onAddTask={handleAddTask} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-white/10 px-4 py-3 text-sm text-zinc-400">
              <span>{currentProject?.key ?? "Workspace"}</span>
              <span>{liveTasks.length} tasks</span>
              <span>Progress <span className="text-white">{progressPercent}%</span></span>
              <div className="h-1.5 w-32 rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: `${progressPercent}%` }} /></div>
              <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-zinc-200" type="button">View Sprint Report</button>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function OnboardingStep({ step, title, body, state }: { step: number; title: string; body: string; state: "done" | "active" | "pending" }) {
  const done = state === "done";
  const active = state === "active";
  return (
    <div className={`relative flex gap-4 rounded-lg border p-3 ${active ? "border-accent/45 bg-accent/10" : "border-transparent"}`}>
      <div className={`grid size-9 shrink-0 place-items-center rounded-full border text-sm font-semibold ${
        done ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-200" : active ? "border-accent bg-accent text-white" : "border-white/15 bg-white/[0.04] text-zinc-400"
      }`}>
        {done ? <BrandIcon name="check" size={18} /> : step}
      </div>
      <div>
        <p className={`text-sm font-semibold ${active ? "text-blue-200" : "text-zinc-200"}`}>{title}</p>
        <p className="mt-1 text-xs text-zinc-500">{body}</p>
      </div>
      <span className={`ml-auto h-fit rounded-md px-2 py-1 text-[10px] ${done ? "bg-emerald-500/15 text-emerald-300" : active ? "bg-accent/15 text-blue-200" : "bg-white/[0.05] text-zinc-500"}`}>
        {done ? "Completed" : active ? "In Progress" : "Pending"}
      </span>
    </div>
  );
}

export function ProductionOnboarding() {
  const router = useRouter();
  const { summary } = useControlPlaneSummary();
  const { agents: apiAgents } = useAgents();
  const { tasks: apiTasks } = useTasks();
  const { usage } = useUsage();
  const { currentProject, bootstrapProject, refetch: refetchProjects } = useProjects();
  const liveAgents = useMemo(() => agentsFromApi(apiAgents, apiTasks, usage.by_agent), [apiAgents, apiTasks, usage.by_agent]);
  const onlineAgents = liveAgents.filter((agent) => agent.status === "Online" || agent.status === "Running").length;
  const [teamId, setTeamId] = useState("default-team");
  const [teamName, setTeamName] = useState("Dipeen Team");
  const [projectName, setProjectName] = useState("Dipeen Launch");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState("");
  const [checkResults, setCheckResults] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [invite, setInvite] = useState<{ code: string; link: string }>({ code: "코드 생성 중…", link: "" });
  const agentConnected = liveAgents.length > 0;
  const byokVerified = onlineAgents > 0;
  const projectReady = Boolean(currentProject);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.auth.me();
        const resolvedTeamId = me.team_id || "default-team";
        if (cancelled) return;
        setTeamId(resolvedTeamId);

        try {
          const team = await api.teams.get(resolvedTeamId);
          if (!cancelled && team.name) setTeamName(team.name);
        } catch {
          // default-team may still be bootstrapping; keep local state.
        }

        const inv = await api.teams.invite(resolvedTeamId);
        if (!cancelled) setInvite({ code: inv.code, link: `${window.location.origin}/onboarding?code=${inv.code}` });
      } catch {
        if (!cancelled) setInvite({ code: "초대 생성 필요", link: "" });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (currentProject?.name) setProjectName(currentProject.name);
    if (currentProject?.repository_url) setRepositoryUrl(currentProject.repository_url);
  }, [currentProject]);

  const copyInvite = () => {
    if (!invite.link) return;
    navigator.clipboard?.writeText(invite.link).catch(() => {});
    setNotice("Invite link copied.");
  };

  const createProductionWorkspace = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      let resolvedTeamId = teamId;
      if (teamId === "default-team" && teamName.trim()) {
        const team = await api.teams.create(teamName.trim());
        auth.setToken(team.token);
        resolvedTeamId = team.team_id;
        setTeamId(team.team_id);
      }

      const project = await bootstrapProject({
        team_name: teamName.trim() || "Dipeen Team",
        project_name: projectName.trim() || "Dipeen Launch",
        repository_url: repositoryUrl.trim() || undefined,
        description: "Production workspace created from Dipeen onboarding.",
      });
      await refetchProjects();

      const inv = await api.teams.invite(resolvedTeamId);
      setInvite({ code: inv.code, link: `${window.location.origin}/onboarding?code=${inv.code}` });
      setNotice(`Production project ready: ${project.name}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const continueToProject = () => {
    if (currentProject?.room_id) {
      router.push(`/meeting/${currentProject.room_id}`);
      return;
    }
    router.push("/");
  };

  const teamStepState = projectReady || teamId !== "default-team" ? "done" : "active";
  const inviteStepState = invite.link ? "done" : teamStepState === "done" ? "active" : "pending";
  const connectStepState = agentConnected ? "done" : invite.link ? "active" : "pending";
  const verifyStepState = byokVerified ? "done" : agentConnected ? "active" : "pending";
  const readyStepState = projectReady && byokVerified ? "done" : projectReady ? "active" : "pending";
  const apiBaseUrl = getApiBaseUrl();
  const lastUpdatedAt = summary?.snapshot_at ?? new Date().toISOString();
  const lastUpdatedLabel = new Date(lastUpdatedAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const verificationRows = [
    { key: "api", label: "API URL", status: "Connected", details: apiBaseUrl },
    { key: "team", label: "Team ID", status: teamId ? "Ready" : "Missing", details: teamId || "—" },
    { key: "project", label: "Project", status: currentProject ? "Ready" : "Required", details: currentProject?.name || "Create production workspace" },
    { key: "agents", label: "Connected Agents", status: agentConnected ? "Detected" : "Waiting", details: `${liveAgents.length} registered / ${onlineAgents} online` },
    { key: "invite", label: "Invite Code", status: invite.link ? "Issued" : "Required", details: invite.code },
  ];

  const runVerificationCheck = async (key: string) => {
    setChecking(key);
    setError("");
    try {
      if (key === "api") await api.controlPlane.summary();
      if (key === "team") await api.auth.me();
      if (key === "project") await api.projects.current();
      if (key === "agents") await api.agents.list();
      if (key === "invite") {
        const inv = await api.teams.invite(teamId);
        setInvite({ code: inv.code, link: `${window.location.origin}/onboarding?code=${inv.code}` });
      }
      setCheckResults((prev) => ({ ...prev, [key]: `Passed ${new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}` }));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setCheckResults((prev) => ({ ...prev, [key]: `Failed: ${message}` }));
    } finally {
      setChecking("");
    }
  };

  return (
    <div className="dp-app">
      <SideNav active="BYOK Onboarding" agents={liveAgents} roomId={currentProject?.room_id} />
      <main className="dp-page-main overflow-auto">
        <TopBar
          detail={
            <span className="inline-flex items-center gap-3">
              <span className="inline-flex items-center gap-2"><BrandIcon name="database" size={14} /> {teamName}</span>
              <span className="inline-flex items-center gap-2"><StatusDot /> All Systems Operational</span>
            </span>
          }
          title="BYOK Onboarding"
        />
      <div className="grid min-h-0 flex-1 gap-2 overflow-x-hidden p-3 xl:grid-cols-[310px_minmax(420px,1fr)_minmax(420px,520px)]">
        <Panel className="rounded-xl p-5">
          <h1 className="text-lg font-semibold text-white">Team Onboarding</h1>
          <p className="mt-2 text-sm leading-5 text-zinc-400">Create your team and connect BYOK agents.</p>
          <div className="mt-8 space-y-4">
            <OnboardingStep body={teamId} state={teamStepState} step={1} title="Create Team" />
            <OnboardingStep body={invite.link ? invite.code : "Generate invite code"} state={inviteStepState} step={2} title="Invite Members" />
            <OnboardingStep body={`${liveAgents.length} registered agents`} state={connectStepState} step={3} title="Connect Agents" />
            <OnboardingStep body={`${onlineAgents} online agents`} state={verifyStepState} step={4} title="Verify BYOK Setup" />
            <OnboardingStep body={currentProject?.name || "Create first project"} state={readyStepState} step={5} title="Ready to Work" />
          </div>
          <div className="mt-8 rounded-xl border border-accent/25 bg-accent/10 p-4">
            <BrandIcon className="text-blue-300" name="key" size={22} />
            <p className="mt-3 text-sm font-semibold text-blue-200">Your keys. Your control.</p>
            <p className="mt-1 text-xs leading-5 text-zinc-400">Dipeen never stores your API keys. All keys stay on your machines.</p>
            <Link className="mt-3 inline-flex text-xs text-blue-300" href="/settings">Learn more</Link>
          </div>
        </Panel>
        <section className="space-y-2">
          <Panel className="rounded-xl p-5">
            <h2 className="font-semibold text-white">Production workspace</h2>
            <p className="mt-1 text-sm text-zinc-500">Create a real team and first project before connecting agent nodes.</p>
            <div className="mt-5 grid gap-3 rounded-lg border border-white/10 bg-[#0b0e13] p-4 lg:grid-cols-3">
              <label className="block text-xs text-zinc-500">
                Team name
                <input
                  className="mt-2 w-full rounded-lg border border-white/10 bg-[#080a0f] px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-accent/50"
                  onChange={(event) => setTeamName(event.target.value)}
                  value={teamName}
                />
              </label>
              <label className="block text-xs text-zinc-500">
                Project name
                <input
                  className="mt-2 w-full rounded-lg border border-white/10 bg-[#080a0f] px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-accent/50"
                  onChange={(event) => setProjectName(event.target.value)}
                  value={projectName}
                />
              </label>
              <label className="block text-xs text-zinc-500">
                Repository URL
                <input
                  className="mt-2 w-full rounded-lg border border-white/10 bg-[#080a0f] px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-accent/50"
                  onChange={(event) => setRepositoryUrl(event.target.value)}
                  placeholder="https://github.com/org/repo"
                  value={repositoryUrl}
                />
              </label>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                disabled={busy}
                onClick={() => void createProductionWorkspace()}
                type="button"
              >
                {busy ? "Creating..." : currentProject ? "Sync Production Workspace" : "Create Production Workspace"}
              </button>
              {currentProject && (
                <span className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
                  {currentProject.key} / {currentProject.room_id}
                </span>
              )}
              {notice && <span className="text-xs text-emerald-300">{notice}</span>}
              {error && <span className="text-xs text-red-300">{error}</span>}
            </div>
          </Panel>
          <Panel className="rounded-xl p-5">
            <h2 className="font-semibold text-white">Invite your team</h2>
            <p className="mt-1 text-sm text-zinc-500">Share the real invite code generated by the backend.</p>
            <div className="mt-5 grid gap-5 rounded-lg border border-white/10 bg-[#0b0e13] p-4 lg:grid-cols-[240px_1fr]">
              <div>
                <p className="text-xs text-zinc-500">Team Invite Code</p>
                <p className="mt-3 font-mono text-2xl font-semibold tracking-[0.16em] text-white">{invite.code}</p>
                <div className="mt-4 flex items-center gap-4 text-xs text-zinc-500">
                  <span>24시간 후 만료</span>
                  <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-zinc-200" onClick={copyInvite} type="button">링크 복사</button>
                </div>
              </div>
              <div className="border-white/10 lg:border-l lg:pl-5">
                <p className="text-xs text-zinc-500">Invite link</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <input className="min-w-[180px] flex-1 rounded-lg border border-white/10 bg-[#080a0f] px-3 py-2 text-sm outline-none placeholder:text-zinc-600 focus:border-accent/50" readOnly value={invite.link || ""} />
                  <button className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!invite.link} onClick={copyInvite} type="button">Copy Invite</button>
                </div>
                <p className="mt-5 break-all text-xs text-zinc-500">Invite link: <span className="ml-2 text-blue-300">{invite.link || "—"}</span></p>
              </div>
            </div>
          </Panel>
          <Panel className="rounded-xl p-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-semibold text-white">Connect your agent clients</h2>
                <p className="mt-1 text-sm text-zinc-500">Install the Dipeen Agent Client on each machine and run the connect command.</p>
              </div>
              <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-zinc-200" type="button">View Docs</button>
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
              <div className="rounded-lg border border-white/10 bg-[#07090d]">
                <div className="flex border-b border-white/10 text-sm">
                  {["macOS / Linux", "Windows", "Docker"].map((tab, index) => (
                    <button className={`px-4 py-3 ${index === 0 ? "border-b-2 border-accent text-blue-200" : "text-zinc-500"}`} key={tab} type="button">{tab}</button>
                  ))}
                </div>
                <pre className="overflow-auto p-4 font-mono text-[12px] leading-6 text-zinc-300">{`# 1. Install the Dipeen launcher
python -m pip install -e agent-client

# 2. One-touch local prep: tools, runners, Cloudflare/NAT
dipeen-agent bootstrap --role FE --workspace "<project-path>" --network cloudflare

# 3. Join this team workspace
dipeen-agent connect --code ${invite.code} --api-url ${apiBaseUrl}

# 4. Local BYOK auth (provider keys stay on this machine)
claude
codex login
opencode auth login

# 5. Start the worker
dipeen-agent start`}</pre>
              </div>
              <div className="space-y-3">
                <div className="rounded-lg border border-white/10 bg-[#0b0e13] p-4">
                  <p className="text-sm font-medium text-white">Requirements</p>
                  {["Python 3.11+ and Git", "Node.js LTS for Claude/Codex/opencode CLIs", "cloudflared for Cloudflare tunnel/NAT", "Outbound 443 (HTTPS/WSS)"].map((item) => (
                    <p className="mt-3 flex gap-2 text-xs text-zinc-400" key={item}><BrandIcon className="text-emerald-300" name="check" size={15} />{item}</p>
                  ))}
                </div>
                <div className="rounded-lg border border-white/10 bg-[#0b0e13] p-4">
                  <p className="text-sm font-medium text-white">Need help?</p>
                  <p className="mt-3 text-xs text-blue-300">Troubleshooting guide</p>
                  <p className="mt-3 text-xs text-blue-300">Contact support</p>
                </div>
              </div>
            </div>
          </Panel>
          <Panel className="rounded-xl p-5">
            <h2 className="font-semibold text-white">BYOK Verification Checklist</h2>
            <div className="mt-3 overflow-hidden rounded-lg border border-white/10">
              {verificationRows.map((row) => (
                <div className="grid grid-cols-[170px_150px_1fr_170px_82px] border-b border-white/10 px-3 py-2 text-xs last:border-b-0" key={row.key}>
                  <span className="flex items-center gap-2 text-zinc-200"><BrandIcon className="text-emerald-300" name="check" size={14} />{row.label}</span>
                  <span className="text-emerald-300">{row.status}</span>
                  <span className="truncate text-zinc-500">{row.details}</span>
                  <span className={`truncate ${checkResults[row.key]?.startsWith("Failed") ? "text-red-300" : "text-zinc-500"}`}>{checkResults[row.key] ?? "Not run yet"}</span>
                  <button
                    className="rounded border border-white/10 px-2 py-1 text-zinc-300 disabled:opacity-50"
                    disabled={checking === row.key}
                    onClick={() => void runVerificationCheck(row.key)}
                    type="button"
                  >
                    {checking === row.key ? "Testing" : "Test"}
                  </button>
                </div>
              ))}
            </div>
          </Panel>
        </section>
        <section className="space-y-2">
          <DecisionNudgePanel compact roomId={currentProject?.room_id ?? "general"} variant="light" />
          <Panel className="rounded-xl">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-3">
                <h2 className="font-semibold text-white">Connected agents</h2>
                <span className="rounded-md border border-white/10 bg-white/[0.05] px-2 py-1 text-xs text-zinc-400">{onlineAgents}/10 online</span>
              </div>
              <span className="text-xs text-zinc-500">Last updated: {lastUpdatedLabel}</span>
            </div>
            <AgentNetwork items={liveAgents} networkLabel={`API: ${apiBaseUrl.replace(/^https?:\/\//, "")}`} projectName={currentProject?.name ?? teamName} />
          </Panel>
          <Panel className="rounded-xl p-5">
            <div className="flex items-start gap-3">
              <BrandIcon className="text-emerald-300" name="shield" size={24} />
              <div>
                <p className="font-semibold text-white">Security and Privacy</p>
                <ul className="mt-3 space-y-2 text-sm leading-5 text-zinc-400">
                  <li>Your API keys are encrypted locally and never leave your machine.</li>
                  <li>Dipeen only receives signed requests on your behalf.</li>
                  <li>You can revoke access anytime.</li>
                </ul>
                <Link className="mt-4 inline-flex text-sm text-blue-300" href="/settings">View security model</Link>
              </div>
            </div>
            <button
              className="mt-5 w-full rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-white disabled:opacity-50"
              disabled={!currentProject}
              onClick={continueToProject}
              type="button"
            >
              Continue to Project Room
            </button>
          </Panel>
        </section>
      </div>
      </main>
    </div>
  );
}

function AgentNetwork({ items, networkLabel, projectName }: { items: Agent[]; networkLabel: string; projectName: string }) {
  const slots = [
    { x: "50%", y: "10%", tone: "blue" as Tone },
    { x: "29%", y: "54%", tone: "green" as Tone },
    { x: "71%", y: "54%", tone: "purple" as Tone },
  ];
  const connectedAgents = items.filter((agent) => agent.role !== "PM");
  const nodes = connectedAgents.slice(0, slots.length).map((agent, index) => {
    const slot = slots[index];
    return {
      id: agent.name,
      role: agent.role,
      title: agent.title,
      status: agent.status,
      x: slot.x,
      y: slot.y,
      tone: slot.tone,
    };
  });
  return (
    <div className="relative h-[520px] overflow-hidden bg-[#07090d]" style={{ backgroundImage: "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.08) 1px, transparent 0)", backgroundSize: "14px 14px" }}>
      <svg className="absolute inset-0 size-full text-white/25" preserveAspectRatio="none" viewBox="0 0 700 520">
        <path d="M350 170 C350 250 180 240 160 320" fill="none" stroke="currentColor" strokeDasharray="5 8" />
        <path d="M350 170 C350 250 520 240 560 320" fill="none" stroke="currentColor" strokeDasharray="5 8" />
        <path d="M350 170 L350 80" fill="none" stroke="currentColor" strokeDasharray="5 8" />
      </svg>
      <div className="absolute left-1/2 top-[36%] w-44 -translate-x-1/2 rounded-xl border border-blue-500/35 bg-[#10141c] p-4 text-center shadow-2xl">
        <div className="mx-auto grid size-10 place-items-center rounded-lg bg-accent text-3xl font-black">D</div>
        <div className="mt-3 flex justify-center -space-x-3">
          {items.slice(0, 4).map((agent, index) => (
            <AgentPortrait className="ring-2 ring-[#10141c]" key={`${agent.id}-${index}`} mode="head" role={agent.role} size="xs" />
          ))}
        </div>
        <p className="mt-3 font-semibold text-white">{projectName}</p>
        <p className="text-sm text-zinc-400">Workspace</p>
        <p className="mt-3 flex items-center justify-center gap-2 text-xs text-zinc-500"><StatusDot /> {networkLabel}</p>
      </div>
      {nodes.length === 0 && (
        <div className="absolute left-1/2 top-[62%] w-64 -translate-x-1/2 rounded-xl border border-white/10 bg-white/[0.04] p-4 text-center text-sm text-zinc-400">
          연결된 에이전트가 없습니다. 초대 코드를 사용해 로컬 agent client를 연결하세요.
        </div>
      )}
      {nodes.map((node, index) => (
        <div className={`absolute w-44 -translate-x-1/2 rounded-xl border p-3 ${toneClass[node.tone]}`} key={`${node.id}-${index}`} style={{ left: node.x, top: node.y }}>
          <div className="flex items-start gap-3">
            <AgentPortrait mode="full" role={node.role as AgentRole} size="lg" />
            <div>
              <p className="font-semibold text-white">{node.id}</p>
              <p className="text-xs text-zinc-400">{node.title}</p>
            </div>
            <AgentPortrait className="ml-auto" mode="head" role={node.role as AgentRole} size="xs" />
          </div>
          <p className="mt-3 flex items-center gap-2 text-xs text-emerald-300"><StatusDot status={node.status} /> {node.status}</p>
        </div>
      ))}
      <button className="absolute left-1/2 top-[79%] -translate-x-1/2 rounded-xl border border-amber-200 bg-amber-50 px-8 py-4 text-center text-amber-700" type="button">
        <span className="block text-2xl leading-none">+</span>
        <span className="mt-2 block text-sm font-semibold">Add Agent</span>
        <span className="text-xs text-zinc-500">Invite more machines</span>
      </button>
    </div>
  );
}

export function ProductionMeetingRoom({ roomId = "general" }: { roomId?: string }) {
  const { agents: apiAgents } = useAgents();
  const { tasks: apiTasks } = useTasks();
  const { usage } = useUsage();
  const { messages: chatMessages, sendMessage } = useChat(roomId);
  const { phase, mode, brief, participants, setMeetingMode } = useMeeting(roomId);
  const roomMessages = useMemo(() => chatMessages.map(messageFromChat), [chatMessages]);
  const liveAgents = useMemo(() => agentsFromApi(apiAgents, apiTasks, usage.by_agent), [apiAgents, apiTasks, usage.by_agent]);
  const meetingAgents = useMemo<Agent[]>(() => participants.map((participant) => {
    const role = normalizeRole(participant.role || participant.agent_id);
    return {
      id: participant.agent_id,
      name: participant.agent_id,
      role,
      title: roleTitles[role],
      status: normalizeAgentStatus(participant.status),
      tasks: 0,
      done: 0,
      success: 0,
      tokens: "0",
      location: defaultLocations[role],
    };
  }), [participants]);
  const navAgents = meetingAgents.length ? meetingAgents : liveAgents;
  const modes: Array<{ label: string; value: MeetingMode }> = [
    { label: "Plan", value: "plan" },
    { label: "Brainstorm", value: "brainstorm" },
    { label: "Review", value: "review" },
    { label: "Debate", value: "debate" },
  ];
  const phaseSteps: Array<{ label: string; value: MeetingPhase; tone: Tone }> = [
    { label: "Discussing", value: "DISCUSSING", tone: "blue" },
    { label: "Brief Ready", value: "BRIEF_READY", tone: "yellow" },
    { label: "Executing", value: "EXECUTING", tone: "green" },
  ];
  const briefRecord = asRecord(brief);
  const objectiveText = brief?.brief || stringValue(briefRecord?.objective);
  const successMetrics = stringArray(briefRecord?.success_metrics);
  const risks = stringArray(briefRecord?.risks);
  const briefTasks = brief?.tasks ?? [];
  const meetingTasks = useMemo(() => apiTasks.map(taskFromApi), [apiTasks]);
  const { artifacts: canonicalArtifacts } = useArtifacts();
  const meetingArtifactRows = useMemo(() => {
    const taskIds = new Set(apiTasks.map((task) => task.task_id));
    const scoped = canonicalArtifacts.filter((artifact) => taskIds.has(artifact.task_id));
    return (scoped.length ? scoped : canonicalArtifacts).slice(0, 4);
  }, [apiTasks, canonicalArtifacts]);

  return (
    <div className="dp-app">
      <SideNav active="Goals" agents={navAgents} roomId={roomId} />
      <main className="dp-page-main">
        <TopBar
          detail={
            <span className="inline-flex items-center gap-2">
              <span>#{roomId}</span>
              <span>·</span>
              <span>{navAgents.length + 1} participants</span>
              <span>·</span>
              <span className="text-emerald-600">{phase}</span>
            </span>
          }
          title="Planning Room"
        />
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-4 lg:px-6">
          <div className="flex overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
            {modes.map((tab) => (
              <button
                className={`min-w-32 px-6 py-3 text-sm ${mode === tab.value ? "bg-blue-600 text-white shadow-sm" : "bg-transparent text-slate-500 hover:text-slate-900"}`}
                key={tab.value}
                onClick={() => void setMeetingMode(tab.value)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {phaseSteps.map((step) => (
              <span className={`rounded-xl border px-5 py-3 text-sm ${toneClass[step.tone]} ${phase === step.value ? "ring-1 ring-inset ring-blue-200" : "opacity-70"}`} key={step.value}>{step.label}</span>
            ))}
          </div>
        </div>
        <div className="grid min-h-0 flex-1 gap-2 p-3 xl:grid-cols-[1fr_680px]">
          <Panel className="flex min-h-0 flex-col rounded-xl">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <h1 className="text-lg font-semibold text-white"># {roomId} / Planning Room</h1>
              <div className="flex items-center gap-3 text-sm text-zinc-400"><BrandIcon name="inspect" size={18} /> {navAgents.length + 1} <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-zinc-200" type="button">Summary</button></div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              {roomMessages.length === 0 ? (
                <div className="rounded-xl border border-white/10 bg-white/[0.035] p-6 text-sm text-zinc-500">
                  이 room에는 아직 대화가 없습니다. 메시지를 보내면 같은 room id로 저장됩니다.
                </div>
              ) : (
                <ChatStream rows={roomMessages} />
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                {["What are the risks?", "Estimate for Wave 2?", "Clarify dependencies"].map((prompt) => (
                  <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-zinc-300" key={prompt} onClick={() => void sendMessage(prompt)} type="button">{prompt}</button>
                ))}
              </div>
            </div>
            <Composer onSend={sendMessage} placeholder="Message Planning Room..." />
          </Panel>
          <section className="grid min-h-0 gap-2 xl:grid-cols-[1fr_260px]">
            <Panel className="min-h-0 overflow-hidden rounded-xl">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <h2 className="font-semibold text-white">Brief Panel</h2>
                <button className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-zinc-200" type="button">Open Brief</button>
              </div>
              <BriefSection title="Objective">{objectiveText || "아직 brief가 없습니다. PM-Agent에게 목표를 보내 brief를 생성하세요."}</BriefSection>
              <BriefSection title="Success Metrics">
                {successMetrics.length ? (
                  <ul className="list-inside list-disc space-y-2">
                    {successMetrics.map((metric) => <li key={metric}>{metric}</li>)}
                  </ul>
                ) : (
                  <p className="text-zinc-500">No success metrics reported yet.</p>
                )}
              </BriefSection>
              <BriefSection accent="yellow" title="Risks and Assumptions">
                {risks.length ? (
                  <ul className="list-inside list-disc space-y-2">
                    {risks.map((risk) => <li key={risk}>{risk}</li>)}
                  </ul>
                ) : (
                  <p className="text-zinc-500">No risks reported yet.</p>
                )}
              </BriefSection>
              <BriefSection title="Task Waves">
                <div className="space-y-3">
                  {briefTasks.map((task, index) => (
                    <div className="flex items-center gap-3" key={`${task.subject}-${index}`}>
                      <span className="rounded border border-white/10 px-2 py-1">Brief {index + 1}</span>
                      <span>{task.subject}</span>
                      <span className="ml-auto rounded-full bg-violet-500/25 px-2 py-1 text-violet-200">{task.required_role ?? "Any"}</span>
                    </div>
                  ))}
                  {!briefTasks.length && meetingTasks.slice(0, 4).map((task, index) => (
                    <div className="flex items-center gap-3" key={task.id}>
                      <span className="rounded border border-white/10 px-2 py-1">Task {index + 1}</span>
                      <span>{task.title}</span>
                      <span className="ml-auto rounded-full bg-white/10 px-2 py-1 text-zinc-300">{task.status}</span>
                    </div>
                  ))}
                  {!briefTasks.length && meetingTasks.length === 0 && <p className="text-zinc-500">No tasks created yet.</p>}
                </div>
              </BriefSection>
              <BriefSection title="Canonical Outputs">
                <div className="space-y-3">
                  {meetingArtifactRows.map((artifact) => (
                    <div className="flex items-center gap-3" key={artifact.artifact_id}>
                      <span className="rounded border border-white/10 px-2 py-1">{artifact.type.replaceAll("_", " ")}</span>
                      <span className="min-w-0 flex-1 truncate">{artifact.summary || artifact.title}</span>
                      <span className="rounded-full bg-white/10 px-2 py-1 text-zinc-300">{artifact.status}</span>
                    </div>
                  ))}
                  {meetingArtifactRows.length === 0 && <p className="text-zinc-500">No verified artifacts attached to this planning flow yet.</p>}
                </div>
              </BriefSection>
              <BriefSection title="Agent Readiness">
                <div className="space-y-3">
                  {navAgents.map((agent, index) => (
                    <div className="flex items-center gap-3" key={`${agent.id}-${index}`}>
                      <AgentPortrait mode="head" role={agent.role} size="sm" />
                      <span className="w-24">{agent.name}</span>
                      <span className={agent.status === "Away" ? "text-amber-300" : "text-emerald-300"}>{agent.status}</span>
                      <span className="ml-auto text-zinc-500">{agent.tasks} tasks</span>
                    </div>
                  ))}
                  {navAgents.length === 0 && <p className="text-zinc-500">No agents in roster yet.</p>}
                </div>
              </BriefSection>
            </Panel>
            <Panel className="rounded-xl p-5">
              <h2 className="font-semibold text-white">Participants ({navAgents.length + 1})</h2>
              <div className="mt-8 space-y-8">
                <div className="flex items-center gap-4">
                  <AgentPortrait mode="head" role="Human" size="md" />
                  <div>
                    <p className="font-semibold text-white">Human</p>
                    <p className="text-xs text-zinc-500">Product Manager</p>
                  </div>
                  <span className="ml-auto flex items-center gap-2 text-xs text-zinc-400"><StatusDot />Online</span>
                </div>
                {navAgents.map((agent, index) => (
                  <div className="flex items-center gap-4" key={`${agent.id}-${index}`}>
                    <AgentPortrait mode="head" role={agent.role} size="md" />
                    <div>
                      <p className="font-semibold text-white">{agent.name}</p>
                      <p className="text-xs text-zinc-500">{agent.title}</p>
                    </div>
                    <span className="ml-auto flex items-center gap-2 text-xs text-zinc-400"><StatusDot status={agent.status} />{agent.status}</span>
                  </div>
                ))}
              </div>
              <button className="mt-12 w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-3 text-sm text-zinc-200" type="button">Invite Participant</button>
            </Panel>
          </section>
        </div>
      </main>
    </div>
  );
}

function BriefSection({ title, children, accent }: { title: string; children: ReactNode; accent?: Tone }) {
  return (
    <div className="border-b border-white/10 p-5 text-sm text-zinc-300 last:border-b-0">
      <div className="mb-3 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.08em] text-zinc-400">
        <span className={accent === "yellow" ? "text-amber-300" : ""}>{title}</span>
        <button className="normal-case tracking-normal text-blue-300" type="button">Edit</button>
      </div>
      {children}
    </div>
  );
}

export function ProductionAgentWorkbench() {
  const { agents: apiAgents } = useAgents();
  const { tasks: apiTasks, retryTask, cancelTask } = useTasks();
  const { currentProject } = useProjects();
  const { usage } = useUsage();
  const { logs: hermesLogs } = useHermes("default-team");   // 라이브 실행 로그(LOG_STREAM)
  const [selected, setSelected] = useState("");
  const activeRoomId = currentProject?.room_id ?? "general";
  const liveAgents = useMemo(() => agentsFromApi(apiAgents, apiTasks, usage.by_agent), [apiAgents, apiTasks, usage.by_agent]);
  const selectedAgent = liveAgents.find((agent) => agent.id === selected) ?? liveAgents[0];
  const selectedApiTask = selectedAgent
    ? (apiTasks.find((task) => normalizeRole(task.required_role ?? task.assigned_agent_id ?? undefined) === selectedAgent.role && normalizeTaskStatus(task.status) === "In Progress")
       ?? apiTasks.find((task) => normalizeRole(task.required_role ?? task.assigned_agent_id ?? undefined) === selectedAgent.role))
    : undefined;
  const selectedTask = selectedApiTask ? taskFromApi(selectedApiTask) : undefined;
  const { activities, loading: activityLoading } = useAgentActivity(selectedAgent?.name, selectedApiTask?.task_id, activeRoomId);
  const executionRows = useMemo(() => executionRowsForTask(selectedApiTask, activities), [selectedApiTask, activities]);
  const changedFileRows = useMemo(() => changedFilesForTask(selectedApiTask, activities), [selectedApiTask, activities]);
  const testSummary = useMemo(() => testSummaryForTask(selectedApiTask, activities), [selectedApiTask, activities]);
  const checklist = useMemo(() => checklistForTask(selectedApiTask, activities), [selectedApiTask, activities]);
  const blockers = useMemo(() => blockersForTask(apiTasks, activities), [apiTasks, activities]);
  const selectedRawAgent = selectedAgent ? apiAgents.find((agent) => agent.agent_id === selectedAgent.id) : undefined;

  useEffect(() => {
    if (!selected && liveAgents[0]) setSelected(liveAgents[0].id);
  }, [liveAgents, selected]);

  if (!selectedAgent) {
    return (
      <div className="dp-app">
        <SideNav active="Runs" roomId={activeRoomId} />
        <main className="dp-page-main grid place-items-center p-8 text-center text-sm text-zinc-500">
          연결된 에이전트가 없습니다 — 노드를 연결하면 워크벤치가 채워집니다.
        </main>
      </div>
    );
  }

  return (
    <div className="dp-app">
      <SideNav active="Runs" agents={liveAgents} roomId={activeRoomId} />
      <aside className="hidden w-[340px] shrink-0 border-r border-white/10 bg-[#0a0d12] p-5 min-[1800px]:block">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-400">Agent Pool</p>
          <button className="rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-zinc-200" type="button">+ New Agent</button>
        </div>
        <input className="mt-5 w-full rounded-lg border border-white/10 bg-[#07090d] px-4 py-3 text-sm outline-none placeholder:text-zinc-500" placeholder="Search agents..." />
        <div className="mt-5 space-y-3">
          {liveAgents.map((agent, index) => (
            <button
              className={`w-full rounded-xl border p-4 text-left transition ${selected === agent.id ? "border-accent bg-accent/10" : "border-white/10 bg-white/[0.035] hover:border-white/20"}`}
              key={`${agent.id}-${index}`}
              onClick={() => setSelected(agent.id)}
              type="button"
            >
              <div className="flex items-start gap-4">
                <AgentPortrait mode="head" role={agent.role} size="lg" />
                <div>
                  <p className="text-lg font-semibold text-white">{agent.name}</p>
                  <p className="text-sm text-zinc-400">{agent.title}</p>
                </div>
                <span className={`ml-auto rounded-md px-2 py-1 text-xs ${agent.status === "Running" ? "bg-emerald-500/15 text-emerald-300" : "bg-white/[0.06] text-zinc-400"}`}>{agent.status}</span>
                <StatusDot status={agent.status} />
              </div>
              <div className="mt-5 grid grid-cols-3 border-t border-white/10 pt-4 text-sm">
                <span><span className="block text-zinc-500">Tasks</span><span className="font-semibold text-white">{agent.tasks}</span></span>
                <span><span className="block text-zinc-500">Done</span><span className="font-semibold text-white">{agent.done}</span></span>
                <span><span className="block text-zinc-500">Success</span><span className="font-semibold text-white">{agent.success}%</span></span>
              </div>
            </button>
          ))}
        </div>
        <button className="mt-4 w-full rounded-lg border border-dashed border-white/15 py-3 text-sm text-zinc-400" type="button">+ Add Bulk Agents</button>
      </aside>
      <main className="dp-page-main">
        <TopBar detail={<span className="rounded bg-blue-500/15 px-2 py-1 text-blue-200">Live Execution</span>} title="Run Workbench" />
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="grid min-h-full gap-4 p-4 min-[1800px]:grid-cols-[minmax(0,1fr)_390px]">
            <section className="min-w-0 space-y-4">
              <Panel className="min-w-0 overflow-hidden rounded-xl">
                <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/10 p-5">
                  <div className="flex gap-4">
                    <AgentPortrait mode="full" role={selectedAgent.role} size="hero" />
                    <div>
                      <div className="flex items-center gap-3">
                        <h1 className="text-2xl font-semibold text-white">{selectedAgent.name}</h1>
                        <span className="rounded-md bg-emerald-500/15 px-2 py-1 text-sm text-emerald-300">{selectedAgent.status}</span>
                      </div>
                      <p className="mt-1 text-sm text-zinc-400">{selectedTask?.title ?? "진행 중인 태스크 없음"}</p>
                      <p className="mt-4 text-xs text-zinc-500">
                        {selectedApiTask
                          ? `Task ${selectedApiTask.task_id} | ${selectedApiTask.status} | Updated ${new Date(selectedApiTask.updated_at).toLocaleString("ko-KR")}`
                          : "No task selected"}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-zinc-200 disabled:opacity-40"
                      disabled={!selectedApiTask}
                      onClick={() => { if (selectedApiTask) void retryTask(selectedApiTask.task_id); }}
                      type="button"
                    >Retry</button>
                    <button
                      className="rounded-lg border border-red-500/35 bg-red-500/10 px-4 py-2 text-sm text-red-200 disabled:opacity-40"
                      disabled={!selectedApiTask}
                      onClick={() => { if (selectedApiTask) void cancelTask(selectedApiTask.task_id); }}
                      type="button"
                    >Cancel</button>
                  </div>
                </div>
                <div className="flex border-b border-white/10 px-4">
                  {["Execution", "Files", "Tests", "Checklist"].map((tab, index) => (
                    <button className={`border-b-2 px-5 py-4 text-sm ${index === 0 ? "border-accent text-blue-200" : "border-transparent text-zinc-400"}`} key={tab} type="button">{tab}</button>
                  ))}
                </div>
                <div className="grid gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,340px)]">
                  <div className="rounded-lg border border-white/10 bg-[#07090d]">
                    <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                      <p className="font-semibold text-white">Execution Log</p>
                      <button className="rounded border border-white/10 px-3 py-1.5 text-xs text-zinc-300" type="button">Clear</button>
                    </div>
                    <div className="h-[390px] overflow-auto p-4 font-mono text-[13px] leading-6">
                      {executionRows.length === 0 && (
                        <p className="font-sans text-sm text-zinc-500">
                          {activityLoading ? "Loading execution activity..." : "No execution activity reported for this task yet."}
                        </p>
                      )}
                      {executionRows.map((row, index) => (
                        <span className="block" key={`${row.time}-${row.text}-${index}`}>
                          <span className="text-zinc-500">{row.time}</span>
                          <span className={row.level === "ERROR" ? "ml-4 text-red-300" : row.level === "WARN" ? "ml-4 text-amber-300" : "ml-4 text-emerald-300"}>{row.level}</span>
                          <span className="ml-4 text-zinc-300">{row.text}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-4">
                    <Panel className="rounded-lg p-4">
                      <div className="mb-3 flex items-center justify-between"><p className="font-semibold text-white">Changed Files ({changedFileRows.length})</p><BrandIcon name="inspect" size={16} /></div>
                      <div className="space-y-3">
                        {changedFileRows.length === 0 && <p className="text-sm text-zinc-500">No changed files reported yet.</p>}
                        {changedFileRows.map(({ file, state }, index) => (
                          <div className="flex items-center gap-2 text-sm" key={`${file}-${index}`}>
                            <BrandIcon className={state === "A" ? "text-blue-300" : "text-amber-300"} name="code" size={14} />
                            <span className="min-w-0 flex-1 truncate text-zinc-400">{file}</span>
                            <span className={state === "A" ? "text-emerald-300" : "text-amber-300"}>{state}</span>
                          </div>
                        ))}
                      </div>
                    </Panel>
                    <Panel className="rounded-lg p-4">
                      <p className="font-semibold text-white">Current Branch</p>
                      <p className="mt-4 flex items-center gap-2 text-sm text-zinc-300"><BrandIcon name="branch" size={15} />{selectedApiTask?.branch ?? currentProject?.default_branch ?? "not reported"}</p>
                      <p className="mt-4 text-xs text-zinc-500">Commit</p>
                      <p className="mt-1 text-sm text-white">{stringValue(taskResult(selectedApiTask).commit) ?? "No commit reported"}</p>
                      <p className="mt-4 text-sm text-emerald-300">{selectedApiTask?.status ?? "idle"}</p>
                    </Panel>
                  </div>
                </div>
              </Panel>
              {/* 라이브 실행 로그 — hermes LOG_STREAM. 에이전트가 지금 어디서 무엇을 하는지 추적. */}
              <Panel className="overflow-hidden rounded-xl p-0">
                <div className="h-[300px]">
                  <LogStream logs={hermesLogs} filterTaskId={selectedApiTask?.task_id} />
                </div>
              </Panel>
              <div className="grid gap-4 lg:grid-cols-3">
                <Panel className="rounded-xl p-4">
                  <p className="font-semibold text-white">Test Progress</p>
                  {testSummary ? (
                    <>
                      <div className="mt-6 grid place-items-center">
                        <div className="grid size-32 place-items-center rounded-full bg-[conic-gradient(#34d399_0_var(--test-percent),#3b82f6_var(--test-percent)_95%,#ef4444_95%_100%)]" style={{ "--test-percent": `${testSummary.percent}%` } as CSSProperties}>
                          <div className="grid size-24 place-items-center rounded-full bg-[#101318] text-3xl font-semibold text-white">{testSummary.percent}%</div>
                        </div>
                      </div>
                      <div className="mt-5 grid grid-cols-3 text-center text-sm"><span>{testSummary.passed}</span><span>{testSummary.running}</span><span>{testSummary.failed}</span></div>
                    </>
                  ) : (
                    <p className="mt-6 text-sm leading-6 text-zinc-500">No test summary reported yet.</p>
                  )}
                </Panel>
                <Panel className="rounded-xl p-4">
                  <p className="font-semibold text-white">Task Checklist</p>
                  <div className="mt-4 space-y-2">
                    {checklist.length === 0 && <p className="text-sm text-zinc-500">Select a task to see checklist state.</p>}
                    {checklist.map((item) => (
                      <div className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-sm ${item.done ? "border-transparent" : "border-accent/40 bg-accent/10"}`} key={item.label}>
                        <span className={`grid size-5 place-items-center rounded border ${item.done ? "border-blue-400 bg-blue-500 text-white" : "border-white/20"}`}>{item.done ? <BrandIcon name="check" size={12} /> : ""}</span>
                        <span className="flex-1 text-zinc-300">{item.label}</span>
                        <span className="max-w-28 truncate text-xs text-zinc-500">{item.detail}</span>
                      </div>
                    ))}
                  </div>
                </Panel>
                <Panel className="rounded-xl p-4">
                  <div className="flex items-center justify-between"><p className="font-semibold text-white">Pull Request</p><span className={`rounded px-2 py-1 text-xs ${selectedApiTask?.pr_url ? "bg-emerald-500/15 text-emerald-300" : "bg-white/[0.06] text-zinc-400"}`}>{selectedApiTask?.pr_url ? "Open" : "None"}</span></div>
                  {selectedApiTask?.pr_url ? (
                    <>
                      <p className="mt-6 flex items-center gap-3 text-lg text-white"><BrandIcon className="text-violet-300" name="branch" size={30} />{selectedTask?.pr ?? "PR Created"}</p>
                      <p className="mt-3 text-sm text-zinc-400">{selectedApiTask.subject}</p>
                      <a className="mt-6 inline-flex text-sm text-blue-300" href={selectedApiTask.pr_url} rel="noreferrer" target="_blank">View pull request</a>
                    </>
                  ) : (
                    <p className="mt-6 text-sm leading-6 text-zinc-500">No PR URL reported for this task yet.</p>
                  )}
                </Panel>
              </div>
            </section>
            <Inspector agent={selectedAgent} blockers={blockers} rawAgent={selectedRawAgent} task={selectedApiTask} usage={usage} />
          </div>
        </div>
      </main>
    </div>
  );
}

function Inspector({
  agent,
  rawAgent,
  task,
  usage,
  blockers,
}: {
  agent: Agent;
  rawAgent?: LiveAgent;
  task?: ApiTask;
  usage: UsageSummary;
  blockers: Array<{ id: string; tone: string; title: string; body: string }>;
}) {
  const metadata = asRecord(rawAgent?.metadata_json) ?? {};
  const skills = stringArray(metadata.skills);
  const mcps = stringArray(metadata.mcps);
  const model = stringValue(metadata.model) ?? "Not reported";
  const agentTokens = usage.by_agent[agent.id] ?? rawAgent?.tokens_used_this_month ?? 0;
  return (
    <aside className="space-y-4">
      <Panel className="rounded-xl">
        <div className="grid grid-cols-3 border-b border-white/10 text-sm">
          {["Inspector", "Context", "Activity"].map((tab, index) => (
            <button className={`py-4 ${index === 0 ? "border-b-2 border-accent text-white" : "text-zinc-400"}`} key={tab} type="button">{tab}</button>
          ))}
        </div>
        <div className="space-y-4 p-4">
          <InspectorBlock icon="token" title="Cost and Tokens">
            <div className="grid grid-cols-[1fr_120px] gap-4">
              <div className="space-y-2 text-sm text-zinc-400">
                <p>Total Tokens <span className="float-right text-zinc-200">{formatTokens(usage.total_tokens)}</span></p>
                <p>Today Tokens <span className="float-right text-zinc-200">{formatTokens(usage.today_tokens)}</span></p>
                <p>Agent Tokens <span className="float-right text-zinc-200">{formatTokens(agentTokens)}</span></p>
                <p>Task <span className="float-right max-w-28 truncate text-zinc-200">{task?.task_id ?? "none"}</span></p>
              </div>
              <div className="h-24 rounded-lg bg-[linear-gradient(180deg,rgba(124,92,255,0.35),rgba(124,92,255,0.04)),linear-gradient(135deg,transparent_45%,rgba(167,139,250,0.8)_47%,transparent_49%,transparent_56%,rgba(96,165,250,0.6)_58%,transparent_60%)]" />
            </div>
          </InspectorBlock>
          <InspectorBlock icon="spark" title="Model Routing">
            <div className="rounded-lg bg-blue-500/10 px-3 py-2 text-sm text-blue-200">{model}</div>
            {skills.length > 0 && <p className="mt-3 text-xs text-zinc-500">Skills: {skills.join(", ")}</p>}
          </InspectorBlock>
          <InspectorBlock icon="shield" title="Permissions">
            <div className="grid grid-cols-2 gap-3 text-sm text-zinc-300">
              {(mcps.length ? mcps : ["No MCP tools reported"]).map((item) => (
                <p className="flex items-center gap-2" key={item}><BrandIcon className="text-emerald-300" name="check" size={15} />{item}</p>
              ))}
            </div>
          </InspectorBlock>
          <InspectorBlock icon="review" title="Blockers / Questions">
            <div className="space-y-3">
              {blockers.length === 0 && <p className="text-sm text-zinc-500">No blockers reported.</p>}
              {blockers.map((blocker) => (
                <div
                  className={`rounded-lg border p-3 text-sm text-zinc-300 ${blocker.tone === "red" ? "border-red-500/25 bg-red-500/10" : "border-amber-500/25 bg-amber-500/10"}`}
                  key={blocker.id}
                >
                  <p className="font-semibold text-white">{blocker.title}</p>
                  <p className="mt-1 text-xs text-zinc-400">{blocker.body}</p>
                </div>
              ))}
            </div>
          </InspectorBlock>
        </div>
      </Panel>
    </aside>
  );
}

function InspectorBlock({ icon, title, children }: { icon: BrandIconName; title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-4 flex items-center gap-2 font-semibold text-white"><BrandIcon className="text-blue-300" name={icon} size={18} />{title}</div>
      {children}
    </div>
  );
}

export function ProductionVirtualOffice() {
  const { agents: apiAgents } = useAgents();
  const { tasks: apiTasks } = useTasks();
  const { usage } = useUsage();
  const { currentProject } = useProjects();
  const { summary } = useControlPlaneSummary();
  const activeRoomId = currentProject?.room_id ?? "general";
  const { messages: officeMessages } = useChat(activeRoomId);
  const [selected, setSelected] = useState("");
  const liveAgents = useMemo(() => agentsFromApi(apiAgents, apiTasks, usage.by_agent), [apiAgents, apiTasks, usage.by_agent]);
  const selectedAgent = useMemo(() => liveAgents.find((agent) => agent.id === selected) ?? liveAgents[0], [liveAgents, selected]);
  const selectedApiTask = selectedAgent
    ? (apiTasks.find((task) => normalizeRole(task.required_role ?? task.assigned_agent_id ?? undefined) === selectedAgent.role && normalizeTaskStatus(task.status) === "In Progress")
       ?? apiTasks.find((task) => normalizeRole(task.required_role ?? task.assigned_agent_id ?? undefined) === selectedAgent.role))
    : undefined;
  const selectedTask = selectedApiTask ? taskFromApi(selectedApiTask) : undefined;
  const selectedChangedFiles = changedFilesForTask(selectedApiTask);
  const selectedChecklist = checklistForTask(selectedApiTask);
  const totalTokens = usage.today_tokens || 0;
  const officeTokenCap = 5_000_000;
  const officeUsagePercent = usagePercent(totalTokens, officeTokenCap);
  const liveActivity = useMemo(() => officeMessages.slice(-7).reverse().map(messageFromChat), [officeMessages]);

  useEffect(() => {
    if (!selected && liveAgents[0]) setSelected(liveAgents[0].id);
  }, [liveAgents, selected]);

  return (
    <div className="dp-app">
      <SideNav active="Virtual Office" agents={liveAgents} roomId={activeRoomId} />
      <main className="dp-page-main overflow-auto">
        <TopBar detail={<span>{currentProject?.name ?? "No project"} / <span className="text-emerald-300">{currentProject?.status ?? "waiting"}</span> / {liveAgents.length} Agents</span>} title="Virtual Office" />
        <div className="grid min-w-0 flex-1 gap-3 p-3 xl:min-h-0 xl:grid-cols-[1fr_330px]">
          <section className="grid min-w-0 gap-3 xl:min-h-0 xl:grid-rows-[minmax(520px,1fr)_minmax(230px,auto)]">
            <SpatialOfficeCanvasFrame className="min-h-[520px] rounded-xl">
              <Office3DScene agents={liveAgents} selected={selected} setSelected={setSelected} />
            </SpatialOfficeCanvasFrame>
            <Panel className="grid min-w-0 gap-4 rounded-xl p-4 lg:grid-cols-[260px_minmax(0,1fr)] 2xl:grid-cols-[280px_minmax(260px,1fr)_300px]">
              {selectedAgent ? (
                <div className="flex min-w-0 items-center gap-4 border-white/10 lg:border-r lg:pr-5">
                  <AgentPortrait className="rounded-xl" mode="full" role={selectedAgent.role} size="xl" />
                  <div className="min-w-0">
                    <RoleBadge className="size-9 rounded-lg" role={selectedAgent.role} />
                    <h2 className="mt-2 truncate text-lg font-semibold text-white">{selectedAgent.name}</h2>
                    <p className="mt-2 flex items-center gap-2 text-sm text-zinc-400"><StatusDot status={selectedAgent.status} /> {selectedAgent.status}</p>
                  </div>
                </div>
              ) : (
                <div className="border-white/10 text-sm text-zinc-500 lg:border-r lg:pr-5">No agent selected.</div>
              )}
              <div className="min-w-0 px-0 lg:px-5">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-zinc-500">Current Task</p>
                <div className="mt-3 min-w-0 rounded-lg border border-white/10 bg-white/[0.035] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="min-w-0 text-sm font-semibold text-white">{selectedTask?.title ?? "No task assigned"}</p>
                    <span className="shrink-0 rounded bg-violet-500/15 px-2 py-1 text-xs text-violet-200">{selectedTask?.status ?? "Idle"}</span>
                  </div>
                  <p className="mt-3 break-all text-xs text-zinc-500">{currentProject?.repository_url ?? "No repository"} | {selectedApiTask?.branch ?? currentProject?.default_branch ?? "no branch"}</p>
                  <div className="mt-4 h-1.5 rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: selectedTask?.status === "Done" ? "100%" : selectedTask?.status === "In Progress" ? "62%" : selectedTask ? "20%" : "0%" }} /></div>
                </div>
              </div>
              <div className="grid min-w-0 gap-4 sm:grid-cols-2 lg:col-span-2 2xl:col-span-1">
                <div>
                  <p className="border-b border-accent pb-3 text-sm font-semibold text-blue-200">Context</p>
                  <div className="mt-4 space-y-3 text-sm text-zinc-400">
                    {selectedChangedFiles.slice(0, 3).map((file) => (
                      <p key={file.file}>{file.file} <span className="float-right text-zinc-500">{file.state}</span></p>
                    ))}
                    {selectedChangedFiles.length === 0 && <p>No files reported.</p>}
                  </div>
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">Checklist <span className="float-right text-zinc-500">{selectedChecklist.filter((item) => item.done).length} / {selectedChecklist.length}</span></p>
                  <div className="mt-4 space-y-2 text-sm text-zinc-400">
                    {selectedChecklist.map((item) => (
                      <p className="flex items-center gap-2" key={item.label}><BrandIcon className={item.done ? "text-emerald-300" : "text-zinc-600"} name={item.done ? "check" : "review"} size={14} />{item.label}</p>
                    ))}
                    {selectedChecklist.length === 0 && <p>No task checklist.</p>}
                  </div>
                </div>
              </div>
            </Panel>
          </section>
          <aside className="min-w-0 space-y-3 overflow-visible xl:overflow-auto">
            <Panel className="rounded-xl p-5">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-white">Control Plane</h2>
                <span className="rounded bg-blue-500/15 px-2 py-1 text-xs text-blue-200">Canonical</span>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                {[
                  ["Active runs", summary?.active_runs.length ?? 0],
                  ["Artifacts", summary?.latest_artifacts.length ?? 0],
                  ["Permissions", summary?.pending_permissions.length ?? 0],
                  ["Memory", summary?.memory_candidates.length ?? 0],
                ].map(([label, value]) => (
                  <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3" key={label}>
                    <p className="text-xs text-zinc-500">{label}</p>
                    <p className="mt-2 text-xl font-semibold text-white">{value}</p>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel className="rounded-xl p-5">
              <div className="flex items-center justify-between"><h2 className="font-semibold text-white">Live Activity</h2><span className="rounded bg-emerald-500/15 px-2 py-1 text-xs text-emerald-300">Live</span></div>
              <div className="mt-5 space-y-5">
                {liveActivity.length === 0 && <p className="text-sm text-zinc-500">No room activity yet.</p>}
                {liveActivity.map((item, index) => (
                  <div className="flex gap-3" key={`${item.author}-${index}`}>
                    <AgentPortrait mode="head" role={item.role} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-white">{item.author}</p>
                      <p className="truncate text-xs text-zinc-500">{item.body}</p>
                    </div>
                    <span className="text-xs text-zinc-500">{item.time}</span>
                  </div>
                ))}
              </div>
              <button className="mt-5 text-sm text-blue-300" type="button">View all activity</button>
            </Panel>
            <Panel className="rounded-xl p-5">
              <div className="flex items-center justify-between"><h2 className="font-semibold text-white">Token Usage</h2><button className="rounded border border-white/10 px-2 py-1 text-xs text-zinc-300" type="button">Today</button></div>
              <p className="mt-6 text-3xl font-semibold text-white">{formatTokens(totalTokens)} <span className="text-base font-normal text-zinc-500">/ {formatTokens(officeTokenCap)}</span><span className="float-right text-base text-zinc-400">{officeUsagePercent}%</span></p>
              <div className="mt-4 h-3 rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: `${officeUsagePercent}%` }} /></div>
              <div className="mt-6 space-y-3 text-sm">
                {liveAgents.map((agent, index) => (
                  <div className="flex items-center gap-3" key={`${agent.id}-${index}`}>
                    <span className={`size-2 rounded-full ${roleStyles[agent.role].bg}`} />
                    <span className="flex-1 text-zinc-300">{agent.name}</span>
                    <span className="text-zinc-500">{agent.tokens}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </aside>
        </div>
      </main>
    </div>
  );
}
