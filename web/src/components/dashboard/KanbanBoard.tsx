"use client";

import { useState, useEffect } from "react";
import { useTasks } from "@/hooks/useTasks";
import { useAgents, ROLE_COLOR } from "@/hooks/useAgents";
import { useUsage } from "@/hooks/useUsage";
import { AgentStatusCard } from "./AgentStatusCard";
import { api, type Task } from "@/lib/api";
import { useAgentActivity } from "@/hooks/useAgentActivity";

// ─── Types ────────────────────────────────────────────────────────────────────

type ColStatus = "pending" | "in_progress" | "done" | "error";

const COLUMNS: { key: ColStatus; label: string; accent: string }[] = [
  { key: "pending",     label: "Pending",     accent: "#52525B" },
  { key: "in_progress", label: "In Progress", accent: "#6366F1" },
  { key: "done",        label: "Done",        accent: "#22C55E" },
  { key: "error",       label: "Error",       accent: "#EF4444" },
];

const COMPLEXITY_COLOR: Record<string, string> = {
  trivial: "bg-zinc-700 text-zinc-300",
  normal:  "bg-indigo-900/60 text-indigo-300",
  complex: "bg-amber-900/50 text-amber-300",
};

// ─── New Task Modal ───────────────────────────────────────────────────────────

const ROLE_OPTIONS = [
  { value: "", label: "Auto (PM decides)" },
  { value: "FE", label: "FE — Frontend" },
  { value: "BE", label: "BE — Backend" },
  { value: "QA", label: "QA — Testing" },
];

function NewTaskModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (subject: string, prompt: string, options?: { required_role?: string }) => Promise<unknown>;
}) {
  const [subject, setSubject] = useState("");
  const [prompt, setPrompt] = useState("");
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    if (!subject.trim()) return;
    setBusy(true);
    await onCreate(
      subject.trim(),
      prompt.trim() || subject.trim(),
      role ? { required_role: role } : undefined,
    );
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-96 bg-bg-card border border-border rounded-xl shadow-2xl p-5 space-y-4">
        <h3 className="text-[14px] font-semibold">New Task</h3>
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] text-text-muted mb-1">Subject</label>
            <input
              autoFocus
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="FE: LoginForm 구현"
              className="w-full bg-bg-elevated border border-border rounded-md px-3 py-2 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent/50"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) handleSubmit(); }}
            />
          </div>
          <div>
            <label className="block text-[11px] text-text-muted mb-1">Assigned Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full bg-bg-elevated border border-border rounded-md px-3 py-2 text-[13px] text-text-primary focus:outline-none focus:ring-1 focus:ring-accent/50"
            >
              {ROLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-text-muted mb-1">Prompt (optional)</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="상세 지시사항..."
              rows={3}
              className="w-full bg-bg-elevated border border-border rounded-md px-3 py-2 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent/50 resize-none"
            />
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-[13px] text-text-muted hover:text-text-secondary border border-border rounded-md transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={busy || !subject.trim()}
            className="px-3 py-1.5 text-[13px] bg-accent hover:bg-accent-hover text-white font-medium rounded-md transition-colors disabled:opacity-50"
          >
            {busy ? "Creating..." : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Task Detail Modal ────────────────────────────────────────────────────────

function TaskActivityFeed({ taskId }: { taskId: string }) {
  const { activities, loading } = useAgentActivity(undefined, taskId);

  if (loading) return <p className="text-[11px] text-text-muted animate-pulse py-4">Loading activity...</p>;
  if (activities.length === 0) return <p className="text-[11px] text-text-muted py-4">No activity recorded for this task.</p>;

  return (
    <div className="space-y-1.5 font-mono text-[11px]">
      {activities.map((item) => {
        const m = item.metadata;
        switch (item.kind) {
          case "started":
            return (
              <div key={item.id} className="flex gap-2 text-indigo-400">
                <span className="text-text-muted shrink-0">{item.timestamp}</span>
                <span>▶ started — {String(m.model)}</span>
              </div>
            );
          case "tool_use":
            return (
              <div key={item.id} className="flex gap-2 text-zinc-500">
                <span className="text-text-muted shrink-0">{item.timestamp}</span>
                <span className="text-cyan-400/70">{String(m.tool_name)}</span>
                <span className="text-zinc-600 truncate max-w-[200px]">{String(m.tool_args)}</span>
              </div>
            );
          case "progress":
            return (
              <div key={item.id} className="flex gap-2 text-zinc-500">
                <span className="text-text-muted shrink-0">{item.timestamp}</span>
                <span>⏳ {String(m.elapsed_sec)}s · {String(m.changed_count)} files</span>
              </div>
            );
          case "completed":
            return (
              <div key={item.id} className="flex gap-2 text-emerald-400">
                <span className="text-text-muted shrink-0">{item.timestamp}</span>
                <span>✓ completed · {String(m.changed_count)} files</span>
              </div>
            );
          case "error":
            return (
              <div key={item.id} className="flex gap-2 text-red-400">
                <span className="text-text-muted shrink-0">{item.timestamp}</span>
                <span>✗ {item.text}</span>
              </div>
            );
          default:
            return (
              <div key={item.id} className="flex gap-2 text-zinc-600">
                <span className="text-text-muted shrink-0">{item.timestamp}</span>
                <span>{item.text}</span>
              </div>
            );
        }
      })}
    </div>
  );
}

function TaskDetailModal({ task, onClose }: { task: Task; onClose: () => void }) {
  const [tab, setTab] = useState<"details" | "activity">("details");
  const result = task.result as Record<string, unknown> | null;
  const changedFiles = result?.changed_files as string[] | undefined;
  const keyDecisions = result?.key_decisions as string[] | undefined;
  const blockers = result?.blockers as string[] | undefined;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-[520px] max-h-[80vh] bg-bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b border-border-subtle">
          <div className="space-y-1 min-w-0 pr-4">
            <p className="text-[13px] font-semibold text-text-primary leading-snug">{task.subject}</p>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-text-muted">{task.task_id}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                COMPLEXITY_COLOR[(task.complexity ?? "normal") as keyof typeof COMPLEXITY_COLOR] ?? COMPLEXITY_COLOR.normal
              }`}>
                {task.complexity ?? "normal"}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-secondary transition-colors shrink-0 mt-0.5"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-border-subtle px-5">
          <button
            onClick={() => setTab("details")}
            className={`px-3 py-2 text-[12px] font-medium border-b-2 transition-colors ${
              tab === "details"
                ? "border-accent text-text-primary"
                : "border-transparent text-text-muted hover:text-text-secondary"
            }`}
          >
            Details
          </button>
          <button
            onClick={() => setTab("activity")}
            className={`px-3 py-2 text-[12px] font-medium border-b-2 transition-colors ${
              tab === "activity"
                ? "border-accent text-text-primary"
                : "border-transparent text-text-muted hover:text-text-secondary"
            }`}
          >
            Activity
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
          {tab === "activity" ? (
            <TaskActivityFeed taskId={task.task_id} />
          ) : (
            <>
              {/* Prompt */}
              <div>
                <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest mb-2">Prompt</p>
                <p className="text-[12px] text-text-secondary leading-relaxed whitespace-pre-wrap bg-bg-elevated rounded-md px-3 py-2.5 border border-border/40">
                  {task.prompt}
                </p>
              </div>

              {/* PR link */}
              {task.pr_url && (
                <div>
                  <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest mb-2">Pull Request</p>
                  <a
                    href={task.pr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[12px] text-indigo-400 hover:text-indigo-300 transition-colors font-mono"
                  >
                    {task.pr_url}
                  </a>
                </div>
              )}

              {/* Result artifacts */}
              {changedFiles && changedFiles.length > 0 && (
                <div>
                  <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest mb-2">Changed Files</p>
                  <div className="space-y-1">
                    {changedFiles.map((f, i) => (
                      <p key={i} className="text-[11px] font-mono text-text-secondary bg-bg-elevated rounded px-2 py-1 border border-border/30">
                        {f}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              {keyDecisions && keyDecisions.length > 0 && (
                <div>
                  <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest mb-2">Key Decisions</p>
                  <ul className="space-y-1">
                    {keyDecisions.map((d, i) => (
                      <li key={i} className="text-[12px] text-text-secondary flex gap-2">
                        <span className="text-text-muted shrink-0">·</span>
                        {d}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {blockers && blockers.length > 0 && (
                <div>
                  <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest mb-2">Blockers</p>
                  <ul className="space-y-1">
                    {blockers.map((b, i) => (
                      <li key={i} className="text-[12px] text-red-400 flex gap-2">
                        <span className="shrink-0">⚠</span>
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Task Card ────────────────────────────────────────────────────────────────

function TaskCard({ task, agentLabel, agentColor, agentRole, onCancel, onRetry, onClick }: {
  task: Task;
  agentLabel?: string;
  agentColor?: string;
  agentRole?: string;
  onCancel?: () => void;
  onRetry?: () => void;
  onClick: () => void;
}) {
  const complexity = (task.complexity ?? "normal") as keyof typeof COMPLEXITY_COLOR;
  const prNum = task.pr_url?.split("/").pop();
  const canCancel = task.status === "pending" || task.status === "in_progress";
  const canRetry = task.status === "error" || task.status === "cancelled";

  return (
    <div
      className="bg-bg-elevated border border-border/50 rounded-lg p-3 space-y-2 hover:border-border transition-colors cursor-pointer group/card"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[12px] text-text-secondary leading-snug">{task.subject}</p>
        <div className="flex items-center gap-1 shrink-0">
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${COMPLEXITY_COLOR[complexity] ?? COMPLEXITY_COLOR.normal}`}>
            {complexity[0].toUpperCase()}
          </span>
          {canRetry && onRetry && (
            <button
              onClick={(e) => { e.stopPropagation(); onRetry(); }}
              title="Retry task"
              className="opacity-0 group-hover/card:opacity-100 transition-opacity px-1.5 py-0.5 text-[9px] rounded bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500/30"
            >
              Retry
            </button>
          )}
          {canCancel && onCancel && (
            <button
              onClick={(e) => { e.stopPropagation(); onCancel(); }}
              title="Cancel task"
              className="opacity-0 group-hover/card:opacity-100 transition-opacity p-0.5 text-text-muted hover:text-red-400"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-text-muted font-mono">{task.task_id.slice(0, 10)}</span>
        <div className="flex items-center gap-2">
          {prNum && (
            <span className="text-[10px] text-indigo-400 font-mono">PR #{prNum}</span>
          )}
          {agentLabel && (
            <div className="flex items-center gap-1">
              <span
                className="w-4 h-4 rounded text-[8px] font-bold flex items-center justify-center text-black/80"
                style={{ backgroundColor: agentColor }}
              >
                {agentRole}
              </span>
              <span className="text-[10px] text-text-muted">{agentLabel}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ─── Main ─────────────────────────────────────────────────────────────────────

export function KanbanBoard() {
  const { tasks, loading: tasksLoading, createTask, cancelTask, retryTask } = useTasks();
  const { agents } = useAgents();
  const { usage } = useUsage();
  const [showNewTask, setShowNewTask] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [statusFilter, setStatusFilter] = useState<ColStatus | "all">("all");
  const [agentFilter, setAgentFilter] = useState<string>("all");

  // L-2-2: owner role 확인 (soft auth: null이면 모든 권한 허용)
  const [userRole, setUserRole] = useState<string | null>(null);
  useEffect(() => {
    api.auth.me().then(r => setUserRole(r.role)).catch(() => {});
  }, []);
  const canManage = userRole === null || userRole === "owner";

  // Production UI does not synthesize demo rows; empty API data renders an empty board.
  const isEmpty = !tasksLoading && tasks.length === 0;
  const displayTasks = tasks;

  // Build agent lookup by DB id
  const agentById = new Map(agents.map((a) => [a.id, a]));

  // Apply filters
  const filteredTasks = displayTasks.filter((t) => {
    if (agentFilter !== "all" && t.assigned_agent_id !== agentFilter) return false;
    return true;
  });

  // Group tasks by column status
  const grouped: Record<ColStatus, Task[]> = {
    pending:     [],
    in_progress: [],
    done:        [],
    error:       [],
  };
  for (const t of filteredTasks) {
    const col = (t.status === "cancelled" ? "error" : t.status) as ColStatus;
    if (col in grouped) grouped[col].push(t);
  }

  // When statusFilter is active, hide other columns
  const visibleColumns = statusFilter === "all"
    ? COLUMNS
    : COLUMNS.filter((c) => c.key === statusFilter);

  // Agent stats derived from tasks
  const agentStats = agents.map((a) => {
    const mine = displayTasks.filter((t) => t.assigned_agent_id === a.id);
    return {
      agent: a,
      tasksTotal: mine.length,
      tasksDone: mine.filter((t) => t.status === "done").length,
    };
  });

  const totalTokens = usage.total_tokens;
  const tokenLimit = 150_000;

  return (
    <>
      {showNewTask && (
        <NewTaskModal
          onClose={() => setShowNewTask(false)}
          onCreate={createTask}
        />
      )}
      {selectedTask && (
        <TaskDetailModal task={selectedTask} onClose={() => setSelectedTask(null)} />
      )}

      <div className="flex flex-col h-full overflow-hidden">
        {/* Header */}
        <div className="h-12 flex items-center justify-between px-4 border-b border-border-subtle shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">Board</span>
            {tasksLoading && (
              <span className="text-[11px] text-text-muted animate-pulse">loading...</span>
            )}
            {isEmpty && (
              <span className="text-[10px] text-text-muted bg-bg-elevated px-2 py-0.5 rounded-full">
                아직 태스크가 없습니다
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-[11px] text-text-muted">
              <span className="font-mono">{totalTokens.toLocaleString()}</span>
              <span>/</span>
              <span className="font-mono">{tokenLimit.toLocaleString()} tokens</span>
              <div className="w-24 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.min(100, (totalTokens / tokenLimit) * 100)}%` }}
                />
              </div>
            </div>
            <button
              onClick={() => setShowNewTask(true)}
              className="flex items-center gap-1 px-2.5 py-1 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium rounded-md transition-colors"
            >
              <span>+</span>
              <span>New Task</span>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col">
          {/* Filter bar */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-border-subtle shrink-0">
            <span className="text-[11px] text-text-muted">Filter:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as ColStatus | "all")}
              className="bg-bg-elevated border border-border rounded px-2 py-1 text-[11px] text-text-secondary focus:outline-none focus:ring-1 focus:ring-accent/50"
            >
              <option value="all">All Status</option>
              {COLUMNS.map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
            {agents.length > 0 && (
              <select
                value={agentFilter}
                onChange={(e) => setAgentFilter(e.target.value)}
                className="bg-bg-elevated border border-border rounded px-2 py-1 text-[11px] text-text-secondary focus:outline-none focus:ring-1 focus:ring-accent/50"
              >
                <option value="all">All Agents</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>{a.label || a.agent_id}</option>
                ))}
              </select>
            )}
            {(statusFilter !== "all" || agentFilter !== "all") && (
              <button
                onClick={() => { setStatusFilter("all"); setAgentFilter("all"); }}
                className="text-[11px] text-text-muted hover:text-text-secondary transition-colors"
              >
                Clear
              </button>
            )}
          </div>

          {/* Kanban columns */}
          <div className="flex gap-3 p-4 overflow-x-auto flex-1 min-h-0">
            {visibleColumns.map((col) => {
              const colTasks = grouped[col.key];
              return (
                <div key={col.key} className="flex flex-col w-60 shrink-0">
                  {/* Column header */}
                  <div className="flex items-center justify-between mb-2 px-1">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: col.accent }} />
                      <span className="text-[12px] font-medium text-text-secondary">{col.label}</span>
                    </div>
                    <span className="text-[11px] font-mono bg-bg-elevated px-1.5 py-0.5 rounded text-text-muted">
                      {colTasks.length}
                    </span>
                  </div>

                  {/* Cards */}
                  <div className="flex-1 overflow-y-auto space-y-2 pr-0.5">
                    {colTasks.length === 0 ? (
                      <div className="border border-dashed border-border/30 rounded-lg p-4 text-center">
                        <p className="text-[11px] text-text-muted">No tasks</p>
                      </div>
                    ) : (
                      colTasks.map((t) => {
                        const agent = t.assigned_agent_id ? agentById.get(t.assigned_agent_id) : undefined;
                        return (
                          <TaskCard
                            key={t.id}
                            task={t}
                            agentLabel={agent?.label}
                            agentColor={agent?.color ?? ROLE_COLOR[agent?.role?.toUpperCase() ?? ""] ?? undefined}
                            agentRole={agent?.role ?? undefined}
                            onCancel={canManage ? () => cancelTask(t.task_id) : undefined}
                            onRetry={canManage ? () => retryTask(t.task_id) : undefined}
                            onClick={() => setSelectedTask(t)}
                          />
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Agent status footer */}
          {agentStats.length > 0 && (
            <div className="border-t border-border-subtle px-4 py-3 shrink-0">
              <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest mb-3">
                Agents
                <span className="ml-2 font-mono normal-case font-normal">
                  {agentStats.filter(({ agent }) => agent.status !== "offline").length}/{agentStats.length} online
                </span>
              </p>
              <div className="grid grid-cols-2 gap-2">
                {agentStats.map(({ agent, tasksDone, tasksTotal }) => (
                  <AgentStatusCard key={agent.id} agent={agent} tasksDone={tasksDone} tasksTotal={tasksTotal} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
