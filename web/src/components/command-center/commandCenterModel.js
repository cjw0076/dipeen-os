export const ROLE_COLORS = {
  PM: "#FBBF24",
  FE: "#60A5FA",
  BE: "#34D399",
  QA: "#A78BFA",
};

export function roleColor(role) {
  return ROLE_COLORS[String(role || "").toUpperCase()] ?? "#71717A";
}

export function groupTasksByStatus(tasks) {
  return tasks.reduce(
    (acc, task) => {
      const status = task.status === "cancelled" ? "error" : task.status;
      const lane = status in acc ? status : "pending";
      acc[lane].push(task);
      return acc;
    },
    { pending: [], in_progress: [], done: [], error: [] },
  );
}

export function buildCommandCenterMetrics({ agents, tasks, usage, tokenLimit }) {
  const normalizedTasks = tasks ?? [];
  const normalizedAgents = agents ?? [];
  const dailyTokens = usage?.today_tokens ?? usage?.total_tokens ?? 0;

  return {
    onlineAgents: normalizedAgents.filter((agent) => agent.status !== "offline").length,
    workingAgents: normalizedAgents.filter((agent) => agent.status === "working").length,
    activeTasks: normalizedTasks.filter((task) => task.status === "pending" || task.status === "in_progress").length,
    doneTasks: normalizedTasks.filter((task) => task.status === "done").length,
    errorTasks: normalizedTasks.filter((task) => task.status === "error" || task.status === "cancelled").length,
    tokenPercent: Math.min(100, Math.round((dailyTokens / tokenLimit) * 100)),
  };
}
