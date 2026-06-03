"use client";

import { useMemo, useState } from "react";
import { useAgents, ROLE_COLOR, type LiveAgent } from "@/hooks/useAgents";
import { useTasks } from "@/hooks/useTasks";
import { useUsage } from "@/hooks/useUsage";
import { useChat, type ChatMessage } from "@/hooks/useChat";
import { api, type Task } from "@/lib/api";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import { GlassChip, GlassPanel, IconBadge } from "@/components/ui/glass";
import { Sparkline, TokenDonut, UsageBars, WorkflowGraph } from "@/components/ui/data-viz";
import {
  buildCommandCenterMetrics,
  groupTasksByStatus,
  roleColor,
} from "./commandCenterModel.js";

type LaneKey = "pending" | "in_progress" | "done" | "error";

type UiTask = Pick<
  Task,
  "id" | "task_id" | "subject" | "status" | "complexity" | "required_role" | "assigned_agent_id" | "branch" | "pr_url" | "blocked_by"
>;

type Metrics = {
  onlineAgents: number;
  workingAgents: number;
  activeTasks: number;
  doneTasks: number;
  errorTasks: number;
  tokenPercent: number;
};

const TOKEN_LIMIT = 150_000;

const LANES: Array<{ key: LaneKey; label: string; accent: string }> = [
  { key: "pending", label: "Queue", accent: "#71717A" },
  { key: "in_progress", label: "Running", accent: "#6366F1" },
  { key: "done", label: "Done", accent: "#22C55E" },
  { key: "error", label: "Needs Review", accent: "#EF4444" },
];

const FLOW_STEPS = [
  { title: "Create team", state: "ready", detail: "Invite code and owner token" },
  { title: "Connect agents", state: "ready", detail: "Local CLI, BYOK, heartbeat" },
  { title: "Plan with PM", state: "active", detail: "Brief, risks, task waves" },
  { title: "Dispatch work", state: "active", detail: "Branches, logs, PRs" },
  { title: "Review evidence", state: "next", detail: "QA notes and merge signal" },
];

const CLAUDE_ITEMS = [
  "Team invite API and join token lifecycle",
  "Agent heartbeat, capability, and offline recovery events",
  "Meeting brief approval state machine",
  "Task wave dispatch with dependency blocking",
  "Execution logs, changed files, PR metadata, test evidence",
  "Usage aggregation by agent, model, task, and day",
];

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

function StatusDot({ status }: { status: string }) {
  const color = status === "working"
    ? "bg-status-working"
    : status === "idle"
    ? "bg-status-idle"
    : status === "done"
    ? "bg-status-done"
    : status === "error"
    ? "bg-status-error"
    : "bg-zinc-700";
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      {status === "working" && <span className="absolute h-full w-full animate-ping rounded-full bg-status-working opacity-70" />}
      <span className={cx("relative h-2 w-2 rounded-full", color)} />
    </span>
  );
}

function RoleBadge({ role, color }: { role?: string | null; color?: string }) {
  const label = (role || "?").toUpperCase().slice(0, 2);
  return (
    <span
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[10px] font-bold text-black/85"
      style={{ backgroundColor: color || roleColor(role) }}
    >
      {label}
    </span>
  );
}

function TopBar({
  agents,
  metrics,
  totalTokens,
}: {
  agents: LiveAgent[];
  metrics: Metrics;
  totalTokens: number;
}) {
  const tokenItems = agents.slice(0, 4).map((agent) => ({
    label: agent.role || agent.label,
    value: agent.tokens_used_this_month ?? 0,
    color: agent.color || roleColor(agent.role),
  }));

  return (
    <header className="flex min-h-16 shrink-0 flex-wrap items-center gap-3 border-b border-border-subtle bg-bg-primary/95 px-4 py-3">
      <div className="min-w-56">
        <div className="flex items-center gap-2">
          <IconBadge icon="command" tone="blue" size="sm" />
          <div>
            <h1 className="text-[15px] font-semibold leading-tight">Dipeen Command Center</h1>
            <p className="text-[11px] text-text-muted">Team AI Agent Office</p>
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-wrap items-center gap-2">
        {agents.slice(0, 4).map((agent) => (
          <GlassPanel key={agent.agent_id} padding="xs" className="flex min-w-32 items-center gap-2">
            <RoleBadge role={agent.role} color={agent.color} />
            <div className="min-w-0">
              <p className="truncate text-[12px] font-medium">{agent.label}</p>
              <div className="flex items-center gap-1.5 text-[10px] text-text-muted">
                <StatusDot status={agent.status} />
                <span>{agent.status}</span>
              </div>
            </div>
          </GlassPanel>
        ))}
      </div>

      <GlassPanel padding="xs" className="flex min-w-80 items-center gap-4">
        <TokenDonut items={tokenItems} size={58} strokeWidth={7} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between text-[11px] text-text-muted">
            <span>Tokens today</span>
            <span>{metrics.tokenPercent}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-elevated">
            <div className="h-full rounded-full bg-accent" style={{ width: `${metrics.tokenPercent}%` }} />
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-[13px] text-text-primary">{totalTokens.toLocaleString()}</p>
          <p className="text-[10px] text-text-muted">/ {TOKEN_LIMIT.toLocaleString()}</p>
        </div>
      </GlassPanel>
    </header>
  );
}

function MetricStrip({ metrics }: { metrics: Metrics }) {
  const items: Array<{ label: string; value: number; tone: "blue" | "emerald" | "violet" | "amber" | "neutral" | "danger"; icon: BrandIconName }> = [
    { label: "Online", value: metrics.onlineAgents, tone: "emerald" as const, icon: "agent" as BrandIconName },
    { label: "Working", value: metrics.workingAgents, tone: "blue" as const, icon: "play" as BrandIconName },
    { label: "Active Tasks", value: metrics.activeTasks, tone: "violet" as const, icon: "workflow" as BrandIconName },
    { label: "Done", value: metrics.doneTasks, tone: "emerald" as const, icon: "check" as BrandIconName },
    { label: "Risk", value: metrics.errorTasks, tone: metrics.errorTasks ? "danger" : "neutral", icon: "review" as BrandIconName },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
      {items.map((item) => (
        <GlassPanel key={item.label} padding="sm" className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-text-muted">{item.label}</p>
            <p className="mt-1 font-mono text-lg font-semibold text-text-primary">{item.value}</p>
          </div>
          <IconBadge icon={item.icon} tone={item.tone} size="sm" />
        </GlassPanel>
      ))}
    </div>
  );
}

function ChatPanel({
  messages,
  draft,
  setDraft,
  onSend,
}: {
  messages: ChatMessage[];
  draft: string;
  setDraft: (value: string) => void;
  onSend: () => void;
}) {
  return (
    <section className="flex min-h-[520px] flex-col rounded-lg border border-border bg-bg-card">
      <div className="flex h-11 items-center justify-between border-b border-border-subtle px-3">
        <div className="flex items-center gap-2">
          <BrandIcon name="chat" className="h-4 w-4 shrink-0" />
          <span className="text-[13px] font-medium">Shared Room</span>
        </div>
        <GlassChip tone="emerald">live</GlassChip>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {messages.map((message) => (
          <div
            key={message.id}
            className={cx(
              "flex gap-2.5 rounded-md px-2 py-1.5",
              message.sender_type === "human" ? "bg-transparent" : "bg-bg-elevated/45",
            )}
          >
            <RoleBadge role={message.role ?? (message.sender_type === "pm" ? "PM" : undefined)} color={message.color} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate text-[12px] font-semibold" style={{ color: message.sender_type === "human" ? undefined : message.color }}>
                  {message.sender}
                </p>
                <span className="ml-auto text-[10px] text-text-muted">{message.timestamp}</span>
              </div>
              <p className="mt-0.5 whitespace-pre-wrap text-[12px] leading-relaxed text-text-secondary">{message.content}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-border-subtle p-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-elevated px-2.5 py-2">
          <input
            className="min-w-0 flex-1 bg-transparent text-[13px] text-text-primary outline-none placeholder:text-text-muted"
            placeholder="Tell PM-Agent what to plan, dispatch, or inspect..."
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onSend();
            }}
          />
          <button
            className="rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
            disabled={!draft.trim()}
            onClick={onSend}
          >
            Send
          </button>
        </div>
      </div>
    </section>
  );
}

function TaskCard({ task, agent }: { task: UiTask; agent?: LiveAgent }) {
  const taskRole = task.required_role || agent?.role || "?";
  const taskColor = agent?.color || roleColor(taskRole);
  const branchLabel = task.branch || "branch pending";
  return (
    <button className="w-full rounded-lg border border-border/70 bg-bg-elevated/60 p-3 text-left transition-colors hover:border-accent/50">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[12px] font-medium leading-snug text-text-secondary">{task.subject}</p>
        <span className="rounded border border-border bg-bg-card px-1.5 py-0.5 font-mono text-[9px]" style={{ color: taskColor }}>
          {taskRole}
        </span>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-text-muted">
        <span className="font-mono">{task.task_id}</span>
        <span className="truncate">{branchLabel}</span>
      </div>
      {task.blocked_by && (
        <p className="mt-2 rounded bg-yellow-500/10 px-2 py-1 text-[10px] text-yellow-300">blocked by {task.blocked_by}</p>
      )}
    </button>
  );
}

function BoardPanel({
  tasks,
  agents,
}: {
  tasks: UiTask[];
  agents: LiveAgent[];
}) {
  const grouped = groupTasksByStatus(tasks) as Record<LaneKey, UiTask[]>;
  const agentById = new Map(agents.map((agent) => [agent.id, agent]));

  return (
    <section className="rounded-lg border border-border bg-bg-card">
      <div className="flex h-11 items-center justify-between border-b border-border-subtle px-3">
        <div className="flex items-center gap-2">
          <BrandIcon name="board" className="h-4 w-4 shrink-0" />
          <span className="text-[13px] font-medium">Task Waves</span>
        </div>
        <span className="font-mono text-[10px] text-text-muted">{tasks.length} tasks</span>
      </div>
      <div className="grid gap-2 p-3 sm:grid-cols-2 2xl:grid-cols-4">
        {LANES.map((lane) => (
          <div key={lane.key} className="min-h-52 rounded-lg border border-border-subtle bg-bg-primary/40 p-2">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: lane.accent }} />
                <span className="text-[11px] font-medium text-text-secondary">{lane.label}</span>
              </div>
              <span className="rounded bg-bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-text-muted">{grouped[lane.key].length}</span>
            </div>
            <div className="space-y-2">
              {grouped[lane.key].slice(0, 4).map((task) => (
                <TaskCard key={task.id} task={task} agent={task.assigned_agent_id ? agentById.get(task.assigned_agent_id) : undefined} />
              ))}
              {grouped[lane.key].length === 0 && (
                <div className="rounded-md border border-dashed border-border/50 px-3 py-5 text-center text-[11px] text-text-muted">
                  Empty
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AgentWorkbench({ agents, tasks }: { agents: LiveAgent[]; tasks: UiTask[] }) {
  const selected = agents.find((agent) => agent.status === "working") ?? agents[0];
  const currentTask = tasks.find((task) => task.task_id === selected?.current_task_id) ?? tasks.find((task) => task.status === "in_progress");
  const skills = (selected?.metadata_json?.skills as string[] | undefined) ?? [];

  return (
    <section className="rounded-lg border border-border bg-bg-card">
      <div className="flex h-11 items-center justify-between border-b border-border-subtle px-3">
        <div className="flex items-center gap-2">
          <BrandIcon name="code" className="h-4 w-4 shrink-0" />
          <span className="text-[13px] font-medium">Agent Workbench</span>
        </div>
        <GlassChip tone="blue">Live Execution</GlassChip>
      </div>

      <div className="space-y-3 p-3">
        <div className="flex items-start gap-3 rounded-lg border border-border-subtle bg-bg-elevated/45 p-3">
          <RoleBadge role={selected?.role} color={selected?.color} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="text-[13px] font-semibold">{selected?.label ?? "No agent"}</p>
              <StatusDot status={selected?.status ?? "offline"} />
            </div>
            <p className="mt-1 text-[11px] text-text-muted">{currentTask?.subject ?? "Waiting for task assignment"}</p>
          </div>
        </div>

        <div className="rounded-lg border border-border-subtle bg-bg-primary/50 p-3">
          <div className="mb-2 flex items-center justify-between text-[11px]">
            <span className="font-medium text-text-secondary">Execution Log</span>
            <span className="text-text-muted">{currentTask?.status === "in_progress" ? "live" : "idle"}</span>
          </div>
          <div className="font-mono text-[11px] leading-relaxed text-text-muted">
            {currentTask
              ? <p>{currentTask.branch ? `branch ${currentTask.branch}` : "실행 로그 스트리밍 대기 중…"}</p>
              : <p>에이전트가 작업을 시작하면 실행 로그가 여기에 실시간 표시됩니다.</p>}
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-lg border border-border-subtle bg-bg-primary/50 p-3">
            <p className="text-[11px] font-medium text-text-secondary">Skills</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {skills.slice(0, 5).map((skill) => (
                <span key={skill} className="rounded bg-bg-elevated px-2 py-1 text-[10px] text-text-muted">{skill}</span>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-border-subtle bg-bg-primary/50 p-3">
            <p className="text-[11px] font-medium text-text-secondary">PR / Review</p>
            <p className="mt-2 font-mono text-[12px] text-accent-hover">{currentTask?.pr_url ? "PR open" : "PR pending"}</p>
            <p className="mt-1 text-[10px] text-text-muted">QA evidence required before merge</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function FlowPanel() {
  return (
    <section className="rounded-lg border border-border bg-bg-card">
      <div className="flex h-11 items-center justify-between border-b border-border-subtle px-3">
        <div className="flex items-center gap-2">
          <BrandIcon name="workflow" className="h-4 w-4 shrink-0" />
          <span className="text-[13px] font-medium">User Flow</span>
        </div>
        <a className="text-[10px] text-accent-hover hover:underline" href="/onboarding">Open setup</a>
      </div>
      <div className="space-y-2 p-3">
        {FLOW_STEPS.map((step, index) => (
          <div key={step.title} className="flex gap-3 rounded-lg border border-border-subtle bg-bg-primary/45 p-2.5">
            <div
              className={cx(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
                step.state === "ready" && "border-status-done/40 bg-status-done/10 text-status-done",
                step.state === "active" && "border-accent/50 bg-accent/15 text-accent-hover",
                step.state === "next" && "border-border bg-bg-elevated text-text-muted",
              )}
            >
              {index + 1}
            </div>
            <div className="min-w-0">
              <p className="text-[12px] font-medium">{step.title}</p>
              <p className="text-[10px] text-text-muted">{step.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function OperationsInsightPanel({ agents, tasks }: { agents: LiveAgent[]; tasks: UiTask[] }) {
  const grouped = groupTasksByStatus(tasks) as Record<LaneKey, UiTask[]>;
  const tokenItems = agents.slice(0, 5).map((agent) => ({
    label: agent.label,
    value: agent.tokens_used_this_month ?? 0,
    color: agent.color || roleColor(agent.role),
    meta: String(agent.metadata_json?.model ?? "model pending"),
  }));
  const taskCounts = LANES.map((lane) => ({
    label: lane.label,
    value: grouped[lane.key].length,
    color: lane.accent,
  }));
  const trendValues = taskCounts.map((item) => item.value);

  return (
    <section className="rounded-lg border border-border bg-bg-card">
      <div className="flex h-11 items-center justify-between border-b border-border-subtle px-3">
        <div className="flex items-center gap-2">
          <BrandIcon name="graph" className="h-4 w-4 shrink-0" />
          <span className="text-[13px] font-medium">Live Data Widgets</span>
        </div>
        <GlassChip tone="violet">SVG</GlassChip>
      </div>
      <div className="space-y-3 p-3">
        <GlassPanel padding="sm" className="grid grid-cols-[auto_1fr] items-center gap-3">
          <TokenDonut items={taskCounts} />
          <div className="min-w-0">
            <p className="text-[11px] font-medium text-text-secondary">Task distribution</p>
            <p className="mt-1 text-[10px] leading-relaxed text-text-muted">
              Rendered from lane counts, not a static image.
            </p>
            <Sparkline values={trendValues} className="mt-2 h-12 w-full" tone="violet" />
          </div>
        </GlassPanel>
        <GlassPanel padding="sm">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[11px] font-medium text-text-secondary">Agent token usage</p>
            <BrandIcon name="token" className="h-4 w-4 text-accent-hover" />
          </div>
          <UsageBars items={tokenItems} tone="blue" />
        </GlassPanel>
        <GlassPanel padding="sm">
          <p className="mb-2 text-[11px] font-medium text-text-secondary">Workflow load</p>
          <WorkflowGraph counts={taskCounts} />
        </GlassPanel>
      </div>
    </section>
  );
}

function ClaudeHandoffPanel() {
  return (
    <section className="rounded-lg border border-border bg-bg-card">
      <div className="flex h-11 items-center justify-between border-b border-border-subtle px-3">
        <div className="flex items-center gap-2">
          <BrandIcon name="review" className="h-4 w-4 shrink-0" />
          <span className="text-[13px] font-medium">Claude Build Brief</span>
        </div>
        <span className="text-[10px] text-text-muted">docs/claude</span>
      </div>
      <div className="space-y-2 p-3">
        {CLAUDE_ITEMS.map((item) => (
          <div key={item} className="flex items-start gap-2 rounded-md bg-bg-primary/45 px-2.5 py-2">
            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-accent-hover" />
            <p className="text-[11px] leading-relaxed text-text-secondary">{item}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function CommandTabs({ active, onChange }: { active: string; onChange: (value: string) => void }) {
  const tabs = ["Plan", "Execute", "Review", "Setup"];
  return (
    <div className="flex rounded-lg border border-border bg-bg-card p-1">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={cx(
            "min-w-20 rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors",
            active === tab ? "bg-accent text-white" : "text-text-muted hover:bg-bg-elevated hover:text-text-secondary",
          )}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

export function CommandCenter() {
  const { agents: liveAgents } = useAgents();
  const { tasks: liveTasks } = useTasks();
  const { usage } = useUsage();
  const { messages: liveMessages, sendMessage } = useChat("general");
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState("Plan");

  const agents = liveAgents;
  const tasks = liveTasks as UiTask[];
  const messages = liveMessages.slice(-8);
  const usageForMetrics = usage;
  const metrics = useMemo(
    () => buildCommandCenterMetrics({ agents, tasks, usage: usageForMetrics, tokenLimit: TOKEN_LIMIT }) as Metrics,
    [agents, tasks, usageForMetrics],
  );

  function handleSend() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    sendMessage(text);
  }

  async function quickStartPlan() {
    const text = "PM-Agent, current UI flow 기준으로 온보딩 -> 브리프 승인 -> 실행 로그 -> 리뷰까지 필요한 태스크를 만들어줘.";
    setDraft("");
    await api.chat.send(text, "general").catch(() => {});
  }

  return (
    <div className="flex h-full flex-col bg-bg-primary">
      <TopBar agents={agents} metrics={metrics} totalTokens={usageForMetrics.today_tokens} />
      <main className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto flex max-w-[1720px] flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">Current Workspace</h2>
              <p className="text-[12px] text-text-muted">Human plus PM, FE, BE, QA agents in one operating room.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <CommandTabs active={mode} onChange={setMode} />
              <button
                onClick={quickStartPlan}
                className="rounded-lg border border-accent/40 bg-accent/15 px-3 py-2 text-[12px] font-medium text-accent-hover transition-colors hover:bg-accent/25"
              >
                Ask PM to plan
              </button>
            </div>
          </div>

          <MetricStrip metrics={metrics} />

          <div className="command-center-grid gap-4">
            <ChatPanel messages={messages} draft={draft} setDraft={setDraft} onSend={handleSend} />
            <div className="flex flex-col gap-4">
              <BoardPanel tasks={tasks} agents={agents} />
              <AgentWorkbench agents={agents} tasks={tasks} />
            </div>
            <div className="flex flex-col gap-4">
              <FlowPanel />
              <OperationsInsightPanel agents={agents} tasks={tasks} />
              <ClaudeHandoffPanel />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
