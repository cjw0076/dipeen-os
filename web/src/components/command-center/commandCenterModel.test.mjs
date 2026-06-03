import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCommandCenterMetrics,
  groupTasksByStatus,
  roleColor,
} from "./commandCenterModel.js";

test("groups cancelled tasks into the error lane", () => {
  const grouped = groupTasksByStatus([
    { task_id: "T-1", status: "pending" },
    { task_id: "T-2", status: "in_progress" },
    { task_id: "T-3", status: "done" },
    { task_id: "T-4", status: "cancelled" },
  ]);

  assert.equal(grouped.pending.length, 1);
  assert.equal(grouped.in_progress.length, 1);
  assert.equal(grouped.done.length, 1);
  assert.equal(grouped.error.length, 1);
  assert.equal(grouped.error[0].task_id, "T-4");
});

test("summarizes command center health from agents, tasks, and usage", () => {
  const metrics = buildCommandCenterMetrics({
    agents: [
      { agent_id: "pm-agent", status: "idle" },
      { agent_id: "fe-agent", status: "working" },
      { agent_id: "qa-agent", status: "offline" },
    ],
    tasks: [
      { task_id: "T-1", status: "pending" },
      { task_id: "T-2", status: "in_progress" },
      { task_id: "T-3", status: "done" },
      { task_id: "T-4", status: "error" },
    ],
    usage: { today_tokens: 180000 },
    tokenLimit: 150000,
  });

  assert.equal(metrics.onlineAgents, 2);
  assert.equal(metrics.workingAgents, 1);
  assert.equal(metrics.activeTasks, 2);
  assert.equal(metrics.doneTasks, 1);
  assert.equal(metrics.errorTasks, 1);
  assert.equal(metrics.tokenPercent, 100);
});

test("returns stable role colors with a fallback", () => {
  assert.equal(roleColor("FE"), "#60A5FA");
  assert.equal(roleColor("unknown"), "#71717A");
});
