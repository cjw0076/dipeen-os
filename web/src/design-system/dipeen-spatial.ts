export const dipeenSpatialAssets = {
  backgrounds: {
    light: "/assets/dipeen-spatial/backgrounds/office-ivory-light.png",
    dark: "/assets/dipeen-spatial/backgrounds/office-warm-dark.png",
    floorMap: "/assets/dipeen-spatial/backgrounds/office-floor-map.png",
  },
  threeD: {
    officeScene: "/assets/dipeen-spatial/3d/dipeen-office-scene.glb",
  },
  icons: {
    office: "/assets/dipeen-spatial/icons/office.svg",
    agent: "/assets/dipeen-spatial/icons/agent.svg",
    run: "/assets/dipeen-spatial/icons/run.svg",
    artifact: "/assets/dipeen-spatial/icons/artifact.svg",
    permission: "/assets/dipeen-spatial/icons/permission.svg",
    memory: "/assets/dipeen-spatial/icons/memory.svg",
    nudge: "/assets/dipeen-spatial/icons/nudge.svg",
    evidence: "/assets/dipeen-spatial/icons/evidence.svg",
  },
  agentPortraits: {
    human: "/assets/agents/human-manager.png",
    pm: "/assets/agents/pm-agent.png",
    fe: "/assets/agents/fe-agent.png",
    be: "/assets/agents/be-agent.png",
    qa: "/assets/agents/qa-agent.png",
  },
  pageReferences: {
    overview: "/assets/dipeen-spatial/page-references/01-overview-control-tower.png",
    runWorkbench: "/assets/dipeen-spatial/page-references/02-run-workbench.png",
    spatialOffice: "/assets/dipeen-spatial/page-references/03-spatial-office.png",
    meetingBriefRoom: "/assets/dipeen-spatial/page-references/04-meeting-brief-room.png",
    onboardingLauncher: "/assets/dipeen-spatial/page-references/05-onboarding-launcher.png",
    goalFlow: "/assets/dipeen-spatial/page-references/06-goal-flow.png",
    stateGraph: "/assets/dipeen-spatial/page-references/07-state-graph.png",
    settingsProviders: "/assets/dipeen-spatial/page-references/08-settings-providers.png",
    loginAccess: "/assets/dipeen-spatial/page-references/09-login-access.png",
  },
} as const;

export const dipeenSpatialRoles = {
  human: "#2F7DE1",
  pm: "#F2B705",
  fe: "#3F72FF",
  be: "#43B779",
  qa: "#8A66FF",
  system: "#748094",
} as const;

export const dipeenSpatialCopy = {
  en: {
    appName: "Dipeen Control Tower",
    goalProgress: "Goal Progress",
    activeRuns: "Active Runs",
    permissionInbox: "Permission Inbox",
    memoryCandidates: "Memory Candidates",
    approve: "Approve",
    reject: "Reject",
    startRun: "Start Run",
    evidenceReady: "Evidence Ready",
  },
  ko: {
    appName: "디핀 컨트롤 타워",
    goalProgress: "목표 진행",
    activeRuns: "실행 중 작업",
    permissionInbox: "승인함",
    memoryCandidates: "메모리 후보",
    approve: "승인",
    reject: "거절",
    startRun: "실행 시작",
    evidenceReady: "근거 준비됨",
  },
} as const;

export type DipeenSpatialLocale = keyof typeof dipeenSpatialCopy;
export type DipeenSpatialTheme = "light" | "dark";
