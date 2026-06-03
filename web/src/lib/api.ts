import { auth } from "./auth";

const DEFAULT_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getBase(): string {
  if (typeof window !== "undefined") {
    const override = localStorage.getItem("dipeen_api_url");
    if (override?.trim()) return override.trim();
  }
  return DEFAULT_BASE;
}

export function getApiBaseUrl(): string {
  return getBase();
}

export interface Task {
  id: string;
  task_id: string;
  subject: string;
  prompt: string;
  status: string;
  complexity: string | null;
  required_role: string | null;
  required_skills: string[] | null;
  assigned_agent_id: string | null;
  branch: string | null;
  pr_url: string | null;
  result: Record<string, unknown> | null;
  parent_task_id: string | null;
  blocked_by: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface RosterEntry {
  agent_id: string;
  role: string | null;
  status: string;
  current_task_id: string | null;
  available: boolean;
  skills: string[];
  mcps: string[];
  competency: Record<string, number>;
  model: string;
  max_concurrent: number;
  last_heartbeat: string | null;
}

export interface Agent {
  id: string;
  agent_id: string;
  role: string | null;
  status: string;
  current_task_id: string | null;
  last_heartbeat: string | null;
  metadata_json: Record<string, unknown> | null;
  monthly_token_budget: number | null;
  tokens_used_this_month: number;
}

// ProjectAgent 흡수 — team network graph (/api/graph/nodes)
export interface GraphNode {
  id: string;
  node_class: string;      // "agent" | "human" | "team" | ...
  type: string;            // "ai" | "human"
  name: string;
  role: string | null;     // FE | BE | QA | PM
  status: string;          // working | idle | done | error | offline
  accent: string | null;
  stat: string | null;     // 짧은 상태 라벨 (현재 태스크 등)
  pos_x: number;
  pos_y: number;
  parent_id: string | null;
  user_id?: string | null;
}
export interface GraphEdge {
  id: string;
  from: string;
  to: string;
}

// 프로젝트 영속 그래프 노드 — GraphNode 모양 + project_id/agent_id (NodeOut). parent_id="pm"는 PM 별칭.
export interface ProjectNode extends GraphNode {
  project_id: string;
  agent_id: string | null;
}
// create/update 페이로드 (NodeCreate/NodeUpdate). 모두 선택 — 부분 갱신 허용.
export interface ProjectNodeInput {
  name: string;
  type: string;           // ai | human
  role: string;           // FE | BE | QA | …
  status: string;
  accent: string;
  stat: string;
  parent_id: string | null;  // "pm" 별칭 또는 노드 id
  agent_id: string | null;
  pos_x: number;
  pos_y: number;
}

export interface Project {
  id: string;
  team_id: string;
  name: string;
  key: string;
  slug: string;
  status: string;
  description: string | null;
  repository_url: string | null;
  default_branch: string;
  room_id: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DecisionCard {
  id: string;
  team_id: string;
  decision_id: string;
  room_id: string;
  task_id: string | null;
  source_agent_id: string | null;
  decision_type: string;
  question: string;
  context: string | null;
  options: string[] | null;
  recommended_option: string | null;
  risk: string | null;
  confidence: number | null;
  cost_estimate: string | null;
  deadline: string | null;
  status: string;
  answer: string | null;
  note: string | null;
  answered_by: string | null;
  delegated_to: string | null;
  audit_log: Array<Record<string, unknown>> | null;
  created_at: string;
  updated_at: string;
  answered_at: string | null;
  server_receives_provider_keys: boolean;
}

export interface ControlPlaneRun {
  run_id: string;
  task_id: string;
  identity_id: string;
  attempt: number;
  state: string;
  failure_type: string | null;
  created_at: string;
}

export interface ControlPlaneEvent {
  event_id: string;
  event_type: string;
  task_id: string | null;
  run_id: string | null;
  producer: string;
  message: string;
  raw_event_ref: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ArtifactLocation {
  uri: string;
  sha256: string | null;
  media_type: string | null;
}

export interface ArtifactEvidence {
  kind: string;
  passed: boolean;
  message: string | null;
}

export interface ControlPlaneArtifact {
  artifact_id: string;
  type: string;
  status: string;
  task_id: string;
  run_id: string | null;
  producer: {
    identity: string;
    adapter: string | null;
    provider: string | null;
  };
  title: string;
  summary: string;
  locations: ArtifactLocation[];
  evidence: ArtifactEvidence[];
  links: Array<Record<string, string>>;
  created_at: string;
}

export interface StateClaim {
  claim_id: string;
  task_id: string;
  run_id: string;
  producer: string;
  claimed_state: string;
  message: string;
  created_at: string;
}

export interface PermissionRequest {
  permission_request_id: string;
  task_id: string;
  run_id: string;
  requester: string;
  action: string;
  target: string | null;
  reason: string;
  risk: string;
  requires_human_approval: boolean;
  state: string;
}

// 승인 응답 — Core는 실행하지 않는다. side-effect action이면 permission.execute command를 enqueue(worker가 처리).
// executor_mode=dry_run(기본)이면 진짜 PR/push 없이 would_execute receipt만 생성된다.
export interface PermissionApproveResult {
  permission_id: string;
  status: string;                       // approved | rejected
  executor_mode: "dry_run" | "manual_handoff" | "local_execute";
  command_id: string | null;            // side-effect면 enqueue된 command, 아니면 null(review gate)
  message: string;
}

export interface MemoryCandidate {
  memory_candidate_id: string;
  source_artifact_id: string | null;
  memory_type: string;
  proposed_content: string;
  confidence: number;
  promotion_policy: string;
  status: string;
}

export interface ControlPlaneProvider {
  id: string;
  label: string;
  provider: string;
  model: string;
  status: string;
  healthy: boolean;
  last_heartbeat: string | null;
}

export interface SystemHealthItem {
  id: string;
  label: string;
  status: string;
  detail: string;
}

export interface ControlPlaneSummary {
  snapshot_at: string;
  team_id: string;
  goal_progress: {
    total: number;
    done: number;
    running: number;
    ready: number;
    waiting: number;
    blocked: number;
  };
  system_health: SystemHealthItem[];
  active_runs: ControlPlaneRun[];
  pending_permissions: PermissionRequest[];
  pending_decisions: DecisionCard[];
  latest_events: ControlPlaneEvent[];
  latest_artifacts: ControlPlaneArtifact[];
  memory_candidates: MemoryCandidate[];
  providers: ControlPlaneProvider[];
  pending_proposals: CommandProposal[];
  workers: WorkerInfo[];
  queued_commands: WorkerCommand[];
}

export interface Room {
  room_id: string;
  room_type: string;
  ref_id: string | null;
  title: string;
  created_at: string;
}

export interface RoomMessage {
  message_id: string;
  room_id: string;
  sender: { type: string; id: string };
  message_type: string;
  body: string;
  links: Array<{ target_type: string; target_id: string }>;
  created_at: string;
}

// 배정 — UI는 사람·역할·repo만 고른다. role./user./repo./workspace://는 백엔드가 capability로 번역.
export interface AssignmentSpec {
  role?: string | null;
  user?: string | null;
  repo?: string | null;
  workspace_ref?: string | null;
  preferred_worker?: string | null;
  provider?: string | null;
}

export interface CommandProposal {
  proposal_id: string;
  room_id: string;
  message_id: string | null;
  proposed_by: string;
  intent: string;
  provider: string;
  workspace_root: string;
  assignment: AssignmentSpec | null;
  acceptance: Array<Record<string, unknown>>;
  state: string;
  decided_by: string | null;
  task_id: string | null;
  command_id: string | null;
  created_at: string;
}

export interface WorkerWorkspace {
  workspace_ref: string;
  repo?: string | null;
  repo_url?: string | null;
  local_path?: string;
  capabilities?: string[];
}

export interface WorkerInfo {
  worker_id: string;
  capabilities: string[];
  workspaces?: WorkerWorkspace[];
  last_heartbeat: string;
  state: string;
}

// Routing Preview — "이 작업은 누구에게 가는지" (사람-읽는 결과)
export interface RoutingMatch {
  worker_id: string;
  state: string;
  online: boolean;
  user: string | null;
  role: string | null;
  repo: string | null;
  workspace_available: boolean;
}
export interface RoutingPreview {
  required_capabilities: string[];
  matching_workers: RoutingMatch[];
  online_matches: number;
  deliverable: boolean;
  reason: string;
}

// Meeting Closure — 회의 정리물(후보만, 승인 전엔 작업 아님)
export interface ActionCandidate {
  candidate_id: string;
  source_message_ids: string[];
  title: string;
  intent: string;
  scope: Record<string, unknown>;
  suggested_role?: string | null;
  suggested_provider: string;
  acceptance: Array<Record<string, unknown>>;
  state: string;
}
export interface DecisionCandidate {
  candidate_id: string;
  source_message_ids: string[];
  statement: string;
  state: string;
}
export interface MeetingClosurePacket {
  meeting_id: string;
  room_id: string;
  decisions: DecisionCandidate[];
  task_candidates: ActionCandidate[];
  permission_candidates: string[];
  memory_candidates: MemoryCandidate[];
  open_questions: string[];
  created_at: string;
}

export interface WorkerCommand {
  command_id: string;
  command_type: string;
  task_id: string;
  run_id: string;
  provider: string;
  task: Record<string, unknown> | null;
  workspace_ref: string | null;
  repo: string | null;
  workspace_root: string;
  required_capabilities: string[];
  state: string;
  lease_owner: string | null;
  lease_expires_at: string | null;
  permission_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export type WorkspaceMode = "public_demo" | "team" | "production" | "debug";

export interface WorkspaceSpecRepo {
  id: string;
  workspace_ref: string;
}

export interface WorkspaceSpecProject {
  repos: WorkspaceSpecRepo[];
}

export interface WorkspaceSpecTeam {
  roles: string[];
}

export interface WorkspaceSpecUI {
  layout: string;
  panels: string[];
  show_dry_run_banner: boolean;
}

export interface TeamWorkspaceSpec {
  workspace_id: string;
  mode: WorkspaceMode;
  ui: WorkspaceSpecUI;
  project: WorkspaceSpecProject;
  team: WorkspaceSpecTeam;
  policies: Record<string, string>;
  providers: Record<string, string>;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = auth.getToken();
  const res = await fetch(`${getBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (res.status === 401) {
    auth.clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Session expired");
  }
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  workspace: {
    spec: () => apiFetch<TeamWorkspaceSpec>("/api/workspace/spec"),
    apply: (body: { mode: WorkspaceMode | string; workspace_id: string }) =>
      apiFetch<TeamWorkspaceSpec>("/api/workspace/apply", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  controlPlane: {
    summary: () => apiFetch<ControlPlaneSummary>("/api/control-plane/summary"),
  },
  runs: {
    list: (opts?: { taskId?: string; limit?: number }) => {
      const params = new URLSearchParams();
      if (opts?.taskId) params.set("task_id", opts.taskId);
      if (opts?.limit) params.set("limit", String(opts.limit));
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return apiFetch<ControlPlaneRun[]>(`/api/runs${suffix}`);
    },
    get: (runId: string) => apiFetch<ControlPlaneRun>(`/api/runs/${runId}`),
  },
  events: {
    list: (opts?: { taskId?: string; runId?: string; tail?: number }) => {
      const params = new URLSearchParams();
      if (opts?.taskId) params.set("task_id", opts.taskId);
      if (opts?.runId) params.set("run_id", opts.runId);
      if (opts?.tail) params.set("tail", String(opts.tail));
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return apiFetch<ControlPlaneEvent[]>(`/api/events${suffix}`);
    },
  },
  artifacts: {
    list: (opts?: { taskId?: string; runId?: string; type?: string }) => {
      const params = new URLSearchParams();
      if (opts?.taskId) params.set("task_id", opts.taskId);
      if (opts?.runId) params.set("run_id", opts.runId);
      if (opts?.type) params.set("type", opts.type);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return apiFetch<ControlPlaneArtifact[]>(`/api/artifacts${suffix}`);
    },
    get: (artifactId: string) => apiFetch<ControlPlaneArtifact>(`/api/artifacts/${artifactId}`),
  },
  stateClaims: {
    list: (opts?: { taskId?: string; runId?: string }) => {
      const params = new URLSearchParams();
      if (opts?.taskId) params.set("task_id", opts.taskId);
      if (opts?.runId) params.set("run_id", opts.runId);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return apiFetch<StateClaim[]>(`/api/state-claims${suffix}`);
    },
  },
  permissions: {
    list: (status?: string) =>
      apiFetch<PermissionRequest[]>(`/api/permissions${status ? `?status=${status}` : ""}`),
    approve: (permissionRequestId: string) =>
      apiFetch<PermissionApproveResult>(`/api/permissions/${permissionRequestId}/approve`, { method: "POST" }),
    reject: (permissionRequestId: string) =>
      apiFetch<PermissionRequest>(`/api/permissions/${permissionRequestId}/reject`, { method: "POST" }),
  },
  memoryCandidates: {
    list: (status?: string) =>
      apiFetch<MemoryCandidate[]>(`/api/memory-candidates${status ? `?status=${status}` : ""}`),
    promote: (memoryCandidateId: string) =>
      apiFetch<MemoryCandidate>(`/api/memory-candidates/${memoryCandidateId}/promote`, { method: "POST" }),
    reject: (memoryCandidateId: string) =>
      apiFetch<MemoryCandidate>(`/api/memory-candidates/${memoryCandidateId}/reject`, { method: "POST" }),
  },
  rooms: {
    list: () => apiFetch<Room[]>("/api/rooms"),
    create: (body: { room_id: string; room_type?: string; ref_id?: string; title?: string }) =>
      apiFetch<Room>("/api/rooms", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    messages: (roomId: string) => apiFetch<RoomMessage[]>(`/api/rooms/${encodeURIComponent(roomId)}/messages`),
    postMessage: (roomId: string, body: {
      sender_type?: "human" | "agent" | "system";
      sender_id?: string;
      message_type?: string;
      body: string;
      links?: Array<{ target_type: string; target_id: string }>;
    }) =>
      apiFetch<RoomMessage>(`/api/rooms/${encodeURIComponent(roomId)}/messages`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // 회의 '정리' — 메시지를 decision/task/permission/memory/question 후보로 분류. 승인 전엔 작업 아님.
    close: (roomId: string) =>
      apiFetch<MeetingClosurePacket>(`/api/rooms/${encodeURIComponent(roomId)}/close`, { method: "POST" }),
  },
  // 배정 → '이 작업은 누구에게 가는지' 미리보기. UI는 사람·역할·repo만 고르면 됨.
  routing: {
    preview: (assignment: AssignmentSpec, provider = "claude") =>
      apiFetch<RoutingPreview>("/api/routing/preview", {
        method: "POST",
        body: JSON.stringify({ assignment, provider }),
      }),
  },
  proposals: {
    list: (opts?: { roomId?: string; state?: string }) => {
      const params = new URLSearchParams();
      if (opts?.roomId) params.set("room_id", opts.roomId);
      if (opts?.state) params.set("state", opts.state);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return apiFetch<CommandProposal[]>(`/api/proposals${suffix}`);
    },
    create: (body: {
      room_id: string;
      intent: string;
      provider?: string;
      workspace_root?: string;
      proposed_by?: string;
      message_id?: string;
      acceptance?: Array<Record<string, unknown>>;
      assignment?: AssignmentSpec;          // 배정(역할/사람/repo) → 올바른 worker만 lease
    }) =>
      apiFetch<CommandProposal>("/api/proposals", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    // 승인된 작업 후보(회의 정리물) → CommandProposal(배정 포함)
    approveActionCandidate: (body: { room_id: string; candidate: ActionCandidate; proposed_by?: string }) =>
      apiFetch<CommandProposal>("/api/meeting/action-candidates/approve", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    proposePlan: (body: {
      room_id: string;
      proposed_by?: string;
      plan: Array<{
        intent: string;
        provider?: string;
        workspace_root?: string;
        acceptance?: Array<Record<string, unknown>>;
      }>;
    }) =>
      apiFetch<CommandProposal[]>("/api/proposals/plan", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    confirm: (proposalId: string, decidedBy = "user://web") =>
      apiFetch<WorkerCommand>(`/api/proposals/${proposalId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ decided_by: decidedBy }),
      }),
    reject: (proposalId: string, decidedBy = "user://web") =>
      apiFetch<CommandProposal>(`/api/proposals/${proposalId}/reject`, {
        method: "POST",
        body: JSON.stringify({ decided_by: decidedBy }),
      }),
  },
  workers: {
    list: () => apiFetch<WorkerInfo[]>("/api/workers"),
    register: (workerId: string, capabilities: string[], workspaces: WorkerWorkspace[] = []) =>
      apiFetch<WorkerInfo>("/api/workers", {
        method: "POST",
        body: JSON.stringify({ worker_id: workerId, capabilities, workspaces }),
      }),
    heartbeat: (workerId: string) =>
      apiFetch<WorkerInfo>(`/api/workers/${encodeURIComponent(workerId)}/heartbeat`, { method: "POST" }),
    poll: (workerId: string, capabilities?: string[]) =>
      apiFetch<{ command: WorkerCommand | null }>(`/api/workers/${encodeURIComponent(workerId)}/commands/poll`, {
        method: "POST",
        body: JSON.stringify({ capabilities: capabilities ?? [] }),
      }),
    submitResult: (workerId: string, commandId: string, body: {
      status: string;
      summary?: string;
      changed_files?: string[];
      tests_passed?: boolean;
      pr_url?: string;
      key_decisions?: string[];
      runner?: string;
    }) =>
      apiFetch<{ command: WorkerCommand; state: string; failure_type: string | null; reasons: string[] }>(
        `/api/workers/${encodeURIComponent(workerId)}/commands/${encodeURIComponent(commandId)}/result`,
        { method: "POST", body: JSON.stringify(body) },
      ),
  },
  commands: {
    list: (state?: string) => apiFetch<WorkerCommand[]>(`/api/commands${state ? `?state=${state}` : ""}`),
  },
  agents: {
    list: () => apiFetch<Agent[]>("/api/agents"),
    get: (agentId: string) => apiFetch<Agent>(`/api/agents/${agentId}`),
    roster: () =>
      apiFetch<{ agents: RosterEntry[]; snapshot_at: string }>("/api/agents/roster"),
    register: (agentId: string, role: string, skills: string[] = []) =>
      apiFetch<Agent>("/api/agents", {
        method: "POST",
        body: JSON.stringify({
          agent_id: agentId,
          role,
          metadata: { skills, model: "claude-sonnet-4-6" },
        }),
      }),
    sendMessage: (
      agentId: string,
      body: { to_agent_id?: string; task_id?: string; message_type?: string; content: string }
    ) =>
      apiFetch<{ id: string; ok: boolean }>(`/api/agents/${agentId}/message`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    updateCapability: (agentId: string, data: { skills?: string[]; personas?: string[]; model?: string }) =>
      apiFetch<unknown>(`/api/agents/${agentId}/capability`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    delete: (agentId: string) =>
      apiFetch<{ ok: boolean; agent_id: string }>(`/api/agents/${agentId}`, { method: "DELETE" }),
  },
  graph: {
    nodes: () => apiFetch<{ nodes: GraphNode[]; edges: GraphEdge[] }>("/api/graph/nodes"),
  },
  tasks: {
    list: (status?: string) =>
      apiFetch<Task[]>(`/api/tasks${status ? `?status=${status}` : ""}`),
    get: (taskId: string) => apiFetch<Task>(`/api/tasks/${taskId}`),
    create: (subject: string, prompt: string, options?: { required_role?: string; required_skills?: string[] }) =>
      apiFetch<Task>("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ subject, prompt, ...options }),
      }),
    cancel: (taskId: string) =>
      apiFetch<Task>(`/api/tasks/${taskId}/cancel`, { method: "POST" }),
    retry: (taskId: string) =>
      apiFetch<Task>(`/api/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify({ retry: true }),
      }),
    answer: (taskId: string, answer: string) =>
      apiFetch<{ ok: boolean }>(`/api/tasks/${taskId}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer }),
      }),
  },
  decisions: {
    list: (opts?: { status?: string; roomId?: string; taskId?: string; limit?: number }) => {
      const params = new URLSearchParams();
      if (opts?.status) params.set("status", opts.status);
      if (opts?.roomId) params.set("room_id", opts.roomId);
      if (opts?.taskId) params.set("task_id", opts.taskId);
      if (opts?.limit) params.set("limit", String(opts.limit));
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return apiFetch<DecisionCard[]>(`/api/decisions${suffix}`);
    },
    create: (body: {
      room_id?: string;
      task_id?: string;
      source_agent_id?: string;
      decision_type?: string;
      question: string;
      context?: string;
      options?: string[];
      recommended_option?: string;
      risk?: string;
      confidence?: number;
      cost_estimate?: string;
      deadline?: string;
    }) =>
      apiFetch<DecisionCard>("/api/decisions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    answer: (decisionId: string, answer: string, note?: string) =>
      apiFetch<DecisionCard>(`/api/decisions/${decisionId}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer, note }),
      }),
    snooze: (decisionId: string) =>
      apiFetch<DecisionCard>(`/api/decisions/${decisionId}/snooze`, { method: "POST" }),
    delegate: (decisionId: string, delegateTo: string, note?: string) =>
      apiFetch<DecisionCard>(`/api/decisions/${decisionId}/delegate`, {
        method: "POST",
        body: JSON.stringify({ delegate_to: delegateTo, note }),
      }),
  },
  chat: {
    send: (text: string, roomId = "general", senderName?: string) =>
      apiFetch<{ ok: boolean; id: string }>("/api/chat/messages", {
        method: "POST",
        body: JSON.stringify({
          room_id: roomId,
          text,
          sender: senderName || (typeof window !== "undefined" ? localStorage.getItem("dipeen_user_name") : null) || "You",
          sender_type: "user",
        }),
      }),
    history: (roomId = "general", limit = 50, opts?: { sender?: string; taskId?: string }) => {
      const params = new URLSearchParams({ room_id: roomId, limit: String(limit) });
      if (opts?.sender) params.set("sender", opts.sender);
      if (opts?.taskId) params.set("task_id", opts.taskId);
      return apiFetch<Array<{
        id: string;
        room_id: string;
        sender: string;
        sender_type: string;
        color: string;
        text: string;
        task_id?: string;
        metadata_json?: Record<string, unknown>;
        created_at: string;
        timestamp: string;
      }>>(`/api/chat/history?${params.toString()}`);
    },
  },
  usage: {
    summary: (periodDays = 30) =>
      apiFetch<{
        period_days: number;
        total_tokens: number;
        today_tokens: number;
        by_agent: Record<string, number>;
        by_agent_model: Record<string, string>;
        estimated_cost_usd: number;
        snapshot_at: string;
      }>(`/api/usage/summary?period_days=${periodDays}`),
  },
  auth: {
    me: () =>
      apiFetch<{ user_id: string | null; team_id: string | null; role: string | null; name: string | null; avatar_emoji: string | null }>("/api/auth/me"),
    login: (email: string, password: string) =>
      apiFetch<{ access_token: string; token_type: string; user_id: string; team_id: string | null; role: string; name: string }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    signup: (email: string, password: string, name: string) =>
      apiFetch<{ access_token: string; token_type: string; user_id: string; team_id: string | null; role: string; name: string }>("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, name }),
      }),
  },
  teams: {
    create: (name: string) =>
      apiFetch<{ team_id: string; name: string; token: string }>("/api/teams", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    get: (teamId: string) =>
      apiFetch<{ team_id: string; name: string; created_at: string; agent_count: number }>(
        `/api/teams/${teamId}`
      ),
    invite: (teamId: string) =>
      apiFetch<{ code: string; expires_at: string; join_url: string }>(
        `/api/teams/${teamId}/invite`,
        { method: "POST" }
      ),
    join: (code: string) =>
      apiFetch<{ team_id: string; token: string }>(`/api/teams/join?code=${code}`),
  },
  projects: {
    list: () => apiFetch<Project[]>("/api/projects"),
    current: () => apiFetch<Project | null>("/api/projects/current"),
    create: (body: {
      name: string;
      key?: string;
      description?: string;
      repository_url?: string;
      default_branch?: string;
      room_id?: string;
      metadata?: Record<string, unknown>;
    }) =>
      apiFetch<Project>("/api/projects", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    bootstrap: (body: {
      team_name?: string;
      project_name?: string;
      repository_url?: string;
      description?: string;
    }) =>
      apiFetch<Project>("/api/projects/bootstrap", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    get: (projectId: string) => apiFetch<Project>(`/api/projects/${projectId}`),
    update: (projectId: string, body: {
      name?: string;
      status?: string;
      description?: string;
      repository_url?: string;
      default_branch?: string;
      metadata?: Record<string, unknown>;
    }) =>
      apiFetch<Project>(`/api/projects/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    // 영속 조직 그래프 (Leekuejea ProjectAgent 흡수) — node_service가 pm 별칭·cascade reparent·seed 보장.
    // graph() 응답은 /api/graph/nodes와 동일 모양({nodes,edges})이라 ProjectGraph가 두 소스를 같게 소비.
    nodes: (projectId: string) =>
      apiFetch<{ nodes: ProjectNode[]; edges: GraphEdge[] }>(`/api/projects/${projectId}/nodes`),
    createNode: (projectId: string, body: Partial<ProjectNodeInput> = {}) =>
      apiFetch<ProjectNode>(`/api/projects/${projectId}/nodes`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    updateNode: (projectId: string, nodeId: string, body: Partial<ProjectNodeInput>) =>
      apiFetch<ProjectNode>(`/api/projects/${projectId}/nodes/${nodeId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    deleteNode: (projectId: string, nodeId: string) =>
      apiFetch<{ ok: boolean; node_id: string }>(`/api/projects/${projectId}/nodes/${nodeId}`, {
        method: "DELETE",
      }),
    moveNode: (projectId: string, nodeId: string, pos_x: number, pos_y: number) =>
      apiFetch<ProjectNode>(`/api/projects/${projectId}/nodes/${nodeId}/position`, {
        method: "PATCH",
        body: JSON.stringify({ pos_x, pos_y }),
      }),
  },
  meeting: {
    getState: (roomId = "general") =>
      apiFetch<{
        room_id: string;
        phase: string;
        mode: string;
        brief: Record<string, unknown> | null;
        participants: unknown[];
      }>(`/api/meeting/state?room_id=${encodeURIComponent(roomId)}`),
    setMode: (roomId: string, mode: "plan" | "brainstorm" | "review" | "debate") =>
      apiFetch<{ ok: boolean; mode: string }>("/api/meeting/mode", {
        method: "POST",
        body: JSON.stringify({ room_id: roomId, mode }),
      }),
  },
};
