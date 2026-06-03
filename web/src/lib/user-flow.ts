export type ProductFlowStageId =
  | "entry"
  | "onboarding"
  | "control"
  | "meeting"
  | "task-board"
  | "worker"
  | "run-monitor"
  | "artifact-review"
  | "permission"
  | "memory"
  | "completion";

export type ProductFlowState = "done" | "active" | "waiting" | "blocked";

export type ProductFlowStage = {
  id: ProductFlowStageId;
  index: string;
  title: string;
  surface: string;
  href: string;
  owner: "Human" | "Dipeen" | "Worker" | "Agent";
  summary: string;
  outcome: string;
};

export type ProductFlowSignals = {
  hasWorkspace: boolean;
  hasWorker: boolean;
  hasGoal: boolean;
  hasDiscussion: boolean;
  hasProposal: boolean;
  hasQueuedCommand: boolean;
  hasRun: boolean;
  hasRunEvent: boolean;
  hasArtifact: boolean;
  hasVerifiedArtifact: boolean;
  hasPendingPermission: boolean;
  hasPermissionReceipt: boolean;
  hasMemoryCandidate: boolean;
  hasPromotedMemory: boolean;
  goalComplete: boolean;
  hasBlocker: boolean;
};

export const EMPTY_PRODUCT_FLOW_SIGNALS: ProductFlowSignals = {
  hasWorkspace: false,
  hasWorker: false,
  hasGoal: false,
  hasDiscussion: false,
  hasProposal: false,
  hasQueuedCommand: false,
  hasRun: false,
  hasRunEvent: false,
  hasArtifact: false,
  hasVerifiedArtifact: false,
  hasPendingPermission: false,
  hasPermissionReceipt: false,
  hasMemoryCandidate: false,
  hasPromotedMemory: false,
  goalComplete: false,
  hasBlocker: false,
};

export const PRODUCT_FLOW_STAGES: ProductFlowStage[] = [
  {
    id: "entry",
    index: "0",
    title: "Entry",
    surface: "Login / Workspace Select",
    href: "/login",
    owner: "Human",
    summary: "Authenticate, choose a team workspace, then land in the Control Tower.",
    outcome: "A human session is bound to one team workspace.",
  },
  {
    id: "onboarding",
    index: "1",
    title: "Team Onboarding",
    surface: "Onboarding",
    href: "/onboarding",
    owner: "Human",
    summary: "Create or join a workspace, invite humans, register workers, and verify BYOK providers.",
    outcome: "At least one worker is online with declared capabilities.",
  },
  {
    id: "control",
    index: "2",
    title: "Control Tower",
    surface: "Control Tower",
    href: "/app",
    owner: "Dipeen",
    summary: "Observe goal progress, active runs, workers, permission requests, artifacts, and memory candidates.",
    outcome: "The team can create or resume a goal from canonical control-plane state.",
  },
  {
    id: "meeting",
    index: "3",
    title: "Planning Room",
    surface: "Meeting Room",
    href: "/meeting/general",
    owner: "Agent",
    summary: "Human intent becomes discussion, PM analysis, specialist estimates, and command proposals.",
    outcome: "The plan is represented as proposals, not execution.",
  },
  {
    id: "task-board",
    index: "4",
    title: "Task Board",
    surface: "Task Board",
    href: "/app",
    owner: "Dipeen",
    summary: "Confirmed proposals become visible task/run work items grouped by state.",
    outcome: "The human can inspect task status, runs, artifacts, permissions, and memory links.",
  },
  {
    id: "worker",
    index: "5",
    title: "Worker Execution",
    surface: "Worker Pool",
    href: "/app",
    owner: "Worker",
    summary: "A capable local worker polls, leases an approved command, and runs provider CLI or OMO/Hermes.",
    outcome: "Execution happens on the worker device, never in the Web UI.",
  },
  {
    id: "run-monitor",
    index: "6",
    title: "Run Monitor",
    surface: "Run Workbench",
    href: "/dashboard",
    owner: "Dipeen",
    summary: "Stream command, worker, provider, artifact, state-claim, and reconcile events.",
    outcome: "The team sees live evidence for every run transition.",
  },
  {
    id: "artifact-review",
    index: "7",
    title: "Artifact Review",
    surface: "Artifact Viewer",
    href: "/dashboard",
    owner: "Human",
    summary: "Review code patches, test reports, review results, file sets, receipts, and memory candidates.",
    outcome: "Provider output is accepted only after verification and reconciliation.",
  },
  {
    id: "permission",
    index: "8",
    title: "Permission Gate",
    surface: "Permission Inbox",
    href: "/app",
    owner: "Human",
    summary: "Approve or reject push, PR, deploy, secret, integration, and memory-promotion actions.",
    outcome: "Risky work requires a permission receipt before execution.",
  },
  {
    id: "memory",
    index: "9",
    title: "Memory Review",
    surface: "Memory Queue",
    href: "/app",
    owner: "Human",
    summary: "Promote or reject candidate memory from runs, Hermes meetings, repeated errors, or conventions.",
    outcome: "Team memory is candidate-first and human-governed.",
  },
  {
    id: "completion",
    index: "10",
    title: "Goal Completion",
    surface: "Evidence Graph",
    href: "/graph",
    owner: "Dipeen",
    summary: "Close the goal only after tasks, artifacts, permissions, and memory decisions are reconciled.",
    outcome: "The workspace archives a verified evidence trail.",
  },
];

export const PRODUCT_FLOW_INVARIANTS = [
  "Message is not execution.",
  "Proposal is not execution.",
  "Only confirmed proposals enqueue commands.",
  "Web UI never owns provider keys.",
  "Workers execute locally.",
  "Provider output is verified before trust.",
  "Risky actions require permission receipts.",
  "Memory is candidate-first.",
];

export const DEFAULT_PRODUCT_PATH = [
  "Create workspace",
  "Invite/register worker",
  "Create goal",
  "Planning room discussion",
  "PM creates proposals",
  "Human confirms",
  "Worker executes locally",
  "Events/artifacts stream to UI",
  "Human reviews permission",
  "Artifact verified",
  "Memory candidate reviewed",
  "Goal complete",
];

export function buildProductFlowStates(signals: ProductFlowSignals): Record<ProductFlowStageId, ProductFlowState> {
  return {
    entry: signals.hasWorkspace ? "done" : "active",
    onboarding: signals.hasWorker ? "done" : signals.hasWorkspace ? "active" : "waiting",
    control: signals.hasGoal ? "done" : signals.hasWorkspace ? "active" : "waiting",
    meeting: signals.hasProposal ? "done" : signals.hasDiscussion || signals.hasGoal ? "active" : "waiting",
    "task-board": signals.hasQueuedCommand || signals.hasRun ? "done" : signals.hasProposal ? "active" : "waiting",
    worker: signals.hasRun ? "done" : signals.hasQueuedCommand ? "active" : "waiting",
    "run-monitor": signals.hasRunEvent ? "done" : signals.hasRun ? "active" : "waiting",
    "artifact-review": signals.hasVerifiedArtifact ? "done" : signals.hasArtifact ? "active" : "waiting",
    permission: signals.hasPermissionReceipt ? "done" : signals.hasPendingPermission ? "active" : "waiting",
    memory: signals.hasPromotedMemory ? "done" : signals.hasMemoryCandidate ? "active" : "waiting",
    completion: signals.goalComplete ? "done" : signals.hasBlocker ? "blocked" : signals.hasVerifiedArtifact ? "active" : "waiting",
  };
}

export function productFlowProgress(signals: ProductFlowSignals) {
  const states = buildProductFlowStates(signals);
  const done = Object.values(states).filter((state) => state === "done").length;
  return {
    states,
    done,
    total: PRODUCT_FLOW_STAGES.length,
    percent: Math.round((done / PRODUCT_FLOW_STAGES.length) * 100),
  };
}
