"use client";

/**
 * ProjectGraph — 프로젝트 영속 조직 그래프 (@xyflow/react).
 *
 * Leekuejea ProjectAgent 흡수분의 프론트: PM(허브) ↔ 에이전트/사람 노드를 드래그·연결·삭제로
 * 편집하고, 위치/계층이 `/api/projects/{id}/nodes`에 영속한다(이전 SVG 라디얼을 대체).
 * - 드래그 종료 → pos 영속(PATCH …/position)
 * - 핸들 연결 → 부모 재지정(reparent, PATCH …/{id} parent_id)
 * - 노드 삭제 → DELETE(서버가 자식을 부모로 입양, cascade reparent)
 * - WS(node_created=재적재 / node_moved=해당 노드만 갱신)로 라이브
 * dipeen 팔레트: PM=#FBBF24 FE=#60A5FA BE=#34D399 QA=#A78BFA · 상태 점 · 글래스 카드.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  Handle,
  Position,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node as FlowNodeBase,
  type Edge as FlowEdge,
  type NodeProps,
  type Connection,
  type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, type ProjectNode, type GraphEdge, type Task } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import { useAgents, type LiveAgent } from "@/hooks/useAgents";
import { useTasks } from "@/hooks/useTasks";

const ROLE_COLOR: Record<string, string> = {
  PM: "#FBBF24",
  FE: "#60A5FA",
  BE: "#34D399",
  QA: "#A78BFA",
  HUB: "#6366F1",
};
const DEFAULT_COLOR = "#818CF8";

const STATUS_COLOR: Record<string, string> = {
  working: "#34D399",
  active: "#34D399",
  idle: "#FBBF24",
  standby: "#FBBF24",
  done: "#22D3EE",
  error: "#F87171",
  offline: "#52525B",
};

const EDGE_COLOR = "#6366F1";

type AgentData = {
  name: string;
  role: string;
  status: string;
  stat: string;
  color: string;
  isHub: boolean;
  nodeType: string;
  taskTitle?: string;
  taskStatus?: string;
  taskId?: string;
  taskCount: number;
  blockedCount: number;
  runtimeActive: boolean;
};
type FlowNode = FlowNodeBase<AgentData>;
type GraphData = { nodes: ProjectNode[]; edges: GraphEdge[] };

function nodeColor(role: string | null, accent: string | null): string {
  const r = (role || "").toUpperCase();
  return ROLE_COLOR[r] || accent || DEFAULT_COLOR;
}

function isActive(status: string): boolean {
  return status === "working" || status === "active";
}

function normalizeKey(value?: string | null): string {
  return (value || "").trim().toLowerCase();
}

function normalizeRole(value?: string | null): string {
  const raw = normalizeKey(value);
  if (raw.includes("pm") || raw.includes("product") || raw.includes("planning")) return "PM";
  if (raw.includes("be") || raw.includes("back") || raw.includes("server") || raw.includes("api")) return "BE";
  if (raw.includes("qa") || raw.includes("quality") || raw.includes("test")) return "QA";
  if (raw.includes("fe") || raw.includes("front") || raw.includes("ui") || raw.includes("web")) return "FE";
  return (value || "").toUpperCase();
}

function taskKey(task: Task): string {
  return task.task_id || task.id;
}

function shortTaskId(task: Task): string {
  return taskKey(task).split("-")[0] || "task";
}

function isTaskDone(status?: string | null): boolean {
  const raw = normalizeKey(status);
  return raw.includes("done") || raw.includes("complete") || raw.includes("merge") || raw.includes("cancel");
}

function isTaskBlocked(status?: string | null): boolean {
  const raw = normalizeKey(status);
  return raw.includes("block") || raw.includes("error") || raw.includes("fail");
}

function isTaskRunning(status?: string | null): boolean {
  const raw = normalizeKey(status);
  return !isTaskDone(status) && (
    raw.includes("progress") ||
    raw.includes("run") ||
    raw.includes("work") ||
    raw.includes("review") ||
    raw.includes("pending") ||
    raw.includes("assign") ||
    raw.includes("execut")
  );
}

function taskEdgeColor(task?: Task): string {
  if (!task) return EDGE_COLOR;
  if (isTaskBlocked(task.status)) return "#F87171";
  const role = normalizeRole(task.required_role ?? task.assigned_agent_id);
  return ROLE_COLOR[role] || EDGE_COLOR;
}

function truncateLabel(value: string, max = 34): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function taskLabel(task: Task): string {
  const status = task.status || "task";
  return `${status} · ${truncateLabel(task.subject || shortTaskId(task), 28)}`;
}

function buildRuntimeIndex(nodes: ProjectNode[], agents: LiveAgent[], tasks: Task[]) {
  const taskById = new Map<string, Task>();
  const tasksByAgent = new Map<string, Task[]>();
  const tasksByRole = new Map<string, Task[]>();
  const agentById = new Map<string, LiveAgent>();
  const nodeIdByAgent = new Map<string, string>();

  for (const task of tasks) {
    taskById.set(normalizeKey(task.id), task);
    taskById.set(normalizeKey(task.task_id), task);
    const assigned = normalizeKey(task.assigned_agent_id);
    if (assigned) tasksByAgent.set(assigned, [...(tasksByAgent.get(assigned) || []), task]);
    const role = normalizeRole(task.required_role ?? task.assigned_agent_id);
    if (role) tasksByRole.set(role, [...(tasksByRole.get(role) || []), task]);
  }

  for (const agent of agents) {
    agentById.set(normalizeKey(agent.agent_id), agent);
    agentById.set(normalizeKey(agent.id), agent);
  }

  for (const node of nodes) {
    const agentId = normalizeKey(node.agent_id ?? node.id);
    if (agentId) nodeIdByAgent.set(agentId, node.id);
  }

  return { taskById, tasksByAgent, tasksByRole, agentById, nodeIdByAgent };
}

/** 글래스 카드 노드 — 이전 SVG 비주얼을 React Flow 커스텀 노드로 이식. */
function AgentNode({ data, selected }: NodeProps<FlowNode>) {
  const sColor = STATUS_COLOR[data.status] || STATUS_COLOR.offline;
  const size = data.isHub ? 84 : 68;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <Handle type="target" position={Position.Top} style={{ opacity: 0, width: 10, height: 10 }} />
      <div
        className="relative flex items-center justify-center rounded-2xl backdrop-blur-xl transition-transform duration-200"
        style={{
          width: size,
          height: size,
          background: `linear-gradient(145deg, ${data.color}22, rgba(24,24,27,0.72))`,
          border: `1px solid ${data.color}${selected ? "" : "66"}`,
          boxShadow: selected
            ? `0 0 0 2px ${data.color}88, 0 12px 40px ${data.color}33`
            : data.runtimeActive
              ? `0 0 0 1px ${data.color}55, 0 12px 42px ${data.color}26, inset 0 1px 0 rgba(255,255,255,0.08)`
              : `0 8px 28px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06)`,
        }}
      >
        <span className="flex flex-col items-center gap-0.5" style={{ color: data.color }}>
          <BrandIcon
            name={(data.isHub ? "command" : data.nodeType === "human" ? "meeting" : "agent") as BrandIconName}
            size={data.isHub ? 22 : 18}
          />
          <span
            className="font-bold leading-none tracking-tight"
            style={{ fontSize: data.isHub ? 10 : 11 }}
          >
            {data.isHub ? "PM" : (data.role || "AI").toUpperCase()}
          </span>
        </span>
        <span className="absolute -top-0.5 -right-0.5 flex h-3 w-3" title={data.status}>
          {isActive(data.status) && (
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
              style={{ background: sColor }}
            />
          )}
        <span
          className="relative inline-flex h-3 w-3 rounded-full"
          style={{ background: sColor, boxShadow: "0 0 0 2px #09090B" }}
        />
        </span>
        {data.taskCount > 0 && (
          <span
            className="absolute -bottom-1 -right-1 min-w-5 rounded-full border border-black/50 px-1.5 py-0.5 text-center text-[9px] font-bold text-white"
            style={{ background: data.blockedCount > 0 ? "#DC2626" : data.color }}
            title={`${data.taskCount} active task${data.taskCount > 1 ? "s" : ""}`}
          >
            {data.taskCount}
          </span>
        )}
      </div>
      <div className="flex flex-col items-center max-w-[120px]">
        <span className="text-[12px] font-medium text-white/90 truncate max-w-[120px]">{data.name}</span>
        {data.taskTitle ? (
          <span
            className="mt-1 max-w-[148px] rounded-full border px-2 py-0.5 text-[9px] text-white/70"
            style={{ borderColor: `${data.color}66`, background: `${data.color}18` }}
            title={data.taskTitle}
          >
            {data.taskStatus || "task"} · {truncateLabel(data.taskTitle, 18)}
          </span>
        ) : data.stat ? (
          <span className="text-[10px] text-white/40 truncate max-w-[120px]">{data.stat}</span>
        ) : null}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 10, height: 10 }} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

/** 영속 좌표(pos_x/y)가 있으면 그대로, (0,0)이면 PM 중심 방사형으로 배치. */
function buildFlow(
  nodes: ProjectNode[],
  edges: GraphEdge[],
  agents: LiveAgent[] = [],
  tasks: Task[] = [],
): { rfNodes: FlowNode[]; rfEdges: FlowEdge[] } {
  const runtime = buildRuntimeIndex(nodes, agents, tasks);
  const statusById: Record<string, string> = Object.fromEntries(nodes.map((n) => [n.id, n.status]));
  const spokeCount = Math.max(nodes.filter((n) => n.node_class !== "pm").length, 1);
  let si = 0;
  const activeTaskByNode = new Map<string, Task>();
  const pmNode = nodes.find((n) => n.node_class === "pm") ?? nodes[0];

  const rfNodes: FlowNode[] = nodes.map((n) => {
    const isHub = n.node_class === "pm";
    const agentKey = normalizeKey(n.agent_id ?? n.id);
    const liveAgent = runtime.agentById.get(agentKey);
    const nodeRole = normalizeRole(n.role);
    const currentTask = liveAgent?.current_task_id
      ? runtime.taskById.get(normalizeKey(liveAgent.current_task_id))
      : undefined;
    const assignedTasks = agentKey ? runtime.tasksByAgent.get(agentKey) || [] : [];
    const roleTasks = !isHub && assignedTasks.length === 0 && nodeRole
      ? (runtime.tasksByRole.get(nodeRole) || []).filter((task) => !task.assigned_agent_id)
      : [];
    const hubTasks = isHub ? tasks.filter((task) => !task.assigned_agent_id && !isTaskDone(task.status)) : [];
    const candidateTasks = [currentTask, ...assignedTasks, ...roleTasks, ...hubTasks].filter((task): task is Task => Boolean(task));
    const activeTasks = candidateTasks.filter((task) => isTaskRunning(task.status) || isTaskBlocked(task.status));
    const activeTask = activeTasks[0] ?? candidateTasks.find((task) => !isTaskDone(task.status));
    const blockedCount = candidateTasks.filter((task) => isTaskBlocked(task.status) || Boolean(task.blocked_by)).length;
    if (activeTask) activeTaskByNode.set(n.id, activeTask);

    let position = { x: n.pos_x, y: n.pos_y };
    if (n.pos_x === 0 && n.pos_y === 0) {
      if (isHub) {
        position = { x: 0, y: 0 };
      } else {
        const ang = -Math.PI / 2 + (si++ * 2 * Math.PI) / spokeCount;
        position = { x: Math.round(280 * Math.cos(ang)), y: Math.round(230 * Math.sin(ang)) };
      }
    }
    const runtimeStatus = liveAgent?.status ?? n.status;
    const runtimeStat = activeTask
      ? `${shortTaskId(activeTask)} · ${activeTask.status || "task"}`
      : liveAgent?.current_task_id
        ? `${liveAgent.current_task_id} · ${runtimeStatus}`
        : n.stat || "";
    return {
      id: n.id,
      type: "agent",
      position,
      deletable: !isHub,
      data: {
        name: n.name,
        role: n.role || "",
        status: runtimeStatus,
        stat: runtimeStat,
        color: nodeColor(n.role, n.accent),
        isHub,
        nodeType: n.type,
        taskTitle: activeTask?.subject,
        taskStatus: activeTask?.status,
        taskId: activeTask ? taskKey(activeTask) : undefined,
        taskCount: activeTasks.length,
        blockedCount,
        runtimeActive: activeTasks.length > 0 || isActive(runtimeStatus),
      },
    };
  });

  const rfEdges: FlowEdge[] = edges.map((e) => {
    const activeTask = activeTaskByNode.get(e.to);
    const active = Boolean(activeTask) || isActive(statusById[e.from] || "") || isActive(statusById[e.to] || "");
    const blocked = Boolean(activeTask && (isTaskBlocked(activeTask.status) || activeTask.blocked_by));
    const stroke = blocked ? "#F87171" : taskEdgeColor(activeTask);
    return {
      id: e.id,
      source: e.from,
      target: e.to,
      animated: active,
      label: activeTask ? taskLabel(activeTask) : undefined,
      labelStyle: { fill: "#D4D4D8", fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: "#09090B", fillOpacity: 0.72 },
      style: {
        stroke,
        strokeWidth: active ? 2.4 : 1.2,
        opacity: active ? 0.92 : 0.48,
        strokeDasharray: blocked ? "6 4" : undefined,
      },
    };
  });

  const existingEdgeIds = new Set(rfEdges.map((edge) => `${edge.source}->${edge.target}`));
  if (pmNode) {
    for (const node of nodes) {
      const activeTask = activeTaskByNode.get(node.id);
      if (!activeTask || node.id === pmNode.id) continue;
      const edgeKey = `${pmNode.id}->${node.id}`;
      if (existingEdgeIds.has(edgeKey)) continue;
      rfEdges.push({
        id: `task-${taskKey(activeTask)}-${node.id}`,
        source: pmNode.id,
        target: node.id,
        animated: true,
        label: taskLabel(activeTask),
        labelStyle: { fill: "#D4D4D8", fontSize: 10, fontWeight: 600 },
        labelBgStyle: { fill: "#09090B", fillOpacity: 0.72 },
        style: { stroke: taskEdgeColor(activeTask), strokeWidth: 2.2, opacity: 0.88 },
      });
    }
  }

  for (const task of tasks) {
    if (!task.blocked_by || !task.assigned_agent_id) continue;
    const blockedBy = runtime.taskById.get(normalizeKey(task.blocked_by));
    const sourceAgent = normalizeKey(blockedBy?.assigned_agent_id);
    const targetAgent = normalizeKey(task.assigned_agent_id);
    const source = sourceAgent ? runtime.nodeIdByAgent.get(sourceAgent) : undefined;
    const target = targetAgent ? runtime.nodeIdByAgent.get(targetAgent) : undefined;
    if (!source || !target || source === target) continue;
    rfEdges.push({
      id: `blocked-${taskKey(task)}-${source}-${target}`,
      source,
      target,
      animated: true,
      label: `blocked · ${shortTaskId(task)}`,
      labelStyle: { fill: "#FCA5A5", fontSize: 10, fontWeight: 700 },
      labelBgStyle: { fill: "#1F0A0A", fillOpacity: 0.82 },
      style: { stroke: "#F87171", strokeWidth: 2.4, strokeDasharray: "6 4", opacity: 0.9 },
    });
  }

  return { rfNodes, rfEdges };
}

export function ProjectGraph({ projectId }: { projectId?: string }) {
  const { agents } = useAgents();
  const { tasks } = useTasks();
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<FlowEdge>([]);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showMiniMap, setShowMiniMap] = useState(false);
  const runtimeSummary = useMemo(() => {
    const activeTasks = tasks.filter((task) => isTaskRunning(task.status) || isTaskBlocked(task.status));
    const blockedTasks = tasks.filter((task) => isTaskBlocked(task.status) || Boolean(task.blocked_by));
    return {
      activeTasks: activeTasks.length,
      blockedTasks: blockedTasks.length,
    };
  }, [tasks]);

  const load = useCallback(async () => {
    if (!projectId) {
      setGraphData(null);
      setLoading(false);
      return;
    }
    try {
      const data = await api.projects.nodes(projectId);
      setGraphData({ nodes: data.nodes || [], edges: data.edges || [] });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "그래프 로드 실패");
    } finally {
      setLoading(false);
    }
  }, [projectId, setRfNodes, setRfEdges]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    if (!graphData) {
      setRfNodes([]);
      setRfEdges([]);
      return;
    }
    const { rfNodes: nn, rfEdges: ee } = buildFlow(graphData.nodes, graphData.edges, agents, tasks);
    setRfNodes(nn);
    // 첫 마운트 레이스 방지: 커스텀 노드가 측정되기 전에 엣지를 set하면 endpoint 미측정으로
    // 첫 렌더에서 엣지가 누락된다(리로드 후에야 보임). 노드 커밋 다음 프레임에 엣지를 붙인다.
    requestAnimationFrame(() => requestAnimationFrame(() => setRfEdges(ee)));
  }, [agents, graphData, setRfEdges, setRfNodes, tasks]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1536px)");
    const sync = () => setShowMiniMap(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  // WS 라이브: 구조 변화(node_created)=재적재, 이동(node_moved)=해당 노드 위치만(드래그 클로버 방지).
  useEffect(() => {
    const onCreated = () => load();
    const onMoved = (ev: WSEvent) => {
      const id = ev.node_id as string | undefined;
      if (!id) return;
      const px = ev.pos_x as number | undefined;
      const py = ev.pos_y as number | undefined;
      setGraphData((prev) =>
        prev
          ? {
              ...prev,
              nodes: prev.nodes.map((n) =>
                n.id === id ? { ...n, pos_x: px ?? n.pos_x, pos_y: py ?? n.pos_y } : n
              ),
            }
          : prev
      );
      setRfNodes((prev) =>
        prev.map((n) =>
          n.id === id ? { ...n, position: { x: px ?? n.position.x, y: py ?? n.position.y } } : n
        )
      );
    };
    wsManager.on("node_created", onCreated);
    wsManager.on("node_moved", onMoved);
    return () => {
      wsManager.off("node_created", onCreated);
      wsManager.off("node_moved", onMoved);
    };
  }, [load, setRfNodes]);

  const onNodeDragStop = useCallback(
    (_: unknown, node: FlowNode) => {
      if (!projectId) return;
      const posX = Math.round(node.position.x);
      const posY = Math.round(node.position.y);
      setGraphData((prev) =>
        prev
          ? {
              ...prev,
              nodes: prev.nodes.map((n) => (n.id === node.id ? { ...n, pos_x: posX, pos_y: posY } : n)),
            }
          : prev
      );
      api.projects
        .moveNode(projectId, node.id, posX, posY)
        .catch(() => {});
    },
    [projectId]
  );

  // 핸들 연결 = target이 source의 자식이 됨(reparent).
  const onConnect: OnConnect = useCallback(
    (conn: Connection) => {
      if (!projectId || !conn.source || !conn.target || conn.source === conn.target) return;
      setRfEdges((eds) =>
        addEdge(
          { ...conn, animated: false, style: { stroke: EDGE_COLOR, strokeWidth: 1.2, opacity: 0.5 } },
          eds
        )
      );
      api.projects
        .updateNode(projectId, conn.target, { parent_id: conn.source })
        .then(() => load())
        .catch(() => {});
    },
    [projectId, setRfEdges, load]
  );

  const onNodesDelete = useCallback(
    (deleted: FlowNode[]) => {
      if (!projectId) return;
      Promise.all(deleted.map((n) => api.projects.deleteNode(projectId, n.id).catch(() => {}))).then(
        () => load() // 서버의 cascade reparent 결과를 반영
      );
    },
    [projectId, load]
  );

  const addAgent = useCallback(async () => {
    if (!projectId || busy) return;
    setBusy(true);
    try {
      await api.projects.createNode(projectId, {
        name: "새 에이전트",
        role: "FE",
        type: "ai",
        status: "standby",
        parent_id: "pm",
      });
      await load();
    } finally {
      setBusy(false);
    }
  }, [projectId, busy, load]);

  const onlineCount = rfNodes.filter((n) => n.data.status !== "offline").length;
  const activeNodeCount = rfNodes.filter((n) => n.data.runtimeActive).length;

  if (!projectId && !loading) {
    return (
      <div className="grid h-full w-full place-items-center rounded-xl border border-white/5 bg-[#09090B] text-center">
        <div className="text-white/40 text-sm">
          프로젝트가 없습니다 — 온보딩에서 프로젝트를 먼저 생성하세요.
        </div>
      </div>
    );
  }

  return (
    <div
      className="relative h-full w-full overflow-hidden rounded-xl border border-white/5"
      style={{
        background:
          "radial-gradient(1200px 600px at 50% 30%, rgba(99,102,241,0.10), transparent 60%), #09090B",
      }}
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStop={onNodeDragStop}
        onNodesDelete={onNodesDelete}
        colorMode="dark"
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: false }}
        minZoom={0.3}
        maxZoom={1.6}
        defaultEdgeOptions={{ style: { stroke: EDGE_COLOR } }}
      >
        <Background color="rgba(255,255,255,0.05)" gap={28} />
        <Controls showInteractive={false} />
        {showMiniMap && (
          <MiniMap
            pannable
            zoomable
            maskColor="rgba(9,9,11,0.7)"
            nodeColor={(n) => ((n.data as AgentData)?.color as string) || DEFAULT_COLOR}
            style={{ background: "rgba(24,24,27,0.6)", width: 130, height: 96 }}
          />
        )}

        {/* 헤더 */}
        <Panel position="top-left" className="!m-3">
          <div className="rounded-lg bg-black/30 px-3 py-2 backdrop-blur-md border border-white/5">
            <h2 className="text-[14px] font-semibold text-white tracking-tight leading-none">
              Project Graph
            </h2>
            <p className="text-[10px] text-white/40 mt-1">조직 그래프 · 드래그/연결로 편집</p>
          </div>
        </Panel>

        {/* 우상단 상태 + 추가 */}
        <Panel position="top-right" className="!m-3 flex flex-wrap items-center justify-end gap-2">
          <div className="flex items-center gap-2 rounded-full bg-white/5 px-3 py-1.5 backdrop-blur-md border border-white/10">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-[11px] text-white/70 tabular-nums">
              {activeNodeCount}/{onlineCount} active
            </span>
          </div>
          <div className="rounded-full border border-blue-400/20 bg-blue-400/10 px-3 py-1.5 text-[11px] text-blue-100 backdrop-blur-md">
            {runtimeSummary.activeTasks} active tasks
          </div>
          {runtimeSummary.blockedTasks > 0 && (
            <div className="rounded-full border border-red-400/25 bg-red-500/10 px-3 py-1.5 text-[11px] text-red-200 backdrop-blur-md">
              {runtimeSummary.blockedTasks} blocked
            </div>
          )}
          <button
            onClick={addAgent}
            disabled={busy}
            className="rounded-full bg-indigo-500/90 hover:bg-indigo-500 disabled:opacity-50 px-3 py-1.5 text-[11px] font-medium text-white backdrop-blur-md border border-white/10 transition-colors"
          >
            + 에이전트
          </button>
        </Panel>

        {/* 범례 */}
        <Panel position="bottom-left" className="!m-3">
          <div className="flex flex-wrap items-center gap-3 rounded-lg bg-black/30 px-3 py-2 backdrop-blur-md border border-white/5">
            {(["PM", "FE", "BE", "QA"] as const).map((r) => (
              <div key={r} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: ROLE_COLOR[r] }} />
                <span className="text-[10px] text-white/50">{r}</span>
              </div>
            ))}
            <span className="h-4 w-px bg-white/10" />
            <div className="flex items-center gap-1.5">
              <span className="h-px w-5 bg-indigo-400" />
              <span className="text-[10px] text-white/50">org</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="h-px w-5 bg-blue-300 shadow-[0_0_8px_rgba(96,165,250,0.9)]" />
              <span className="text-[10px] text-white/50">active task</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="h-px w-5 border-t border-dashed border-red-300" />
              <span className="text-[10px] text-white/50">blocked</span>
            </div>
          </div>
        </Panel>
      </ReactFlow>

      {/* 상태 메시지 오버레이 */}
      {loading && (
        <div className="absolute inset-0 z-30 grid place-items-center text-white/40 text-sm">
          그래프 로드 중…
        </div>
      )}
      {!loading && error && (
        <div className="absolute inset-0 z-30 grid place-items-center text-center">
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-red-300 text-sm">
            {error}
          </div>
        </div>
      )}
    </div>
  );
}
