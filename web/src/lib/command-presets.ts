export type SlashCommand = {
  readonly name: string;
  readonly title: string;
  readonly description: string;
  readonly placeholder: string;
  readonly template: (input: string) => string;
};

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    name: "/plan",
    title: "Plan work",
    description: "Turn an idea into a task wave.",
    placeholder: "build onboarding with invite and worker setup",
    template: (input) => `Plan this as a Dipeen task wave: ${input || "current workspace goal"}\nInclude owner roles, acceptance evidence, and routing capabilities.`,
  },
  {
    name: "/task",
    title: "Create task",
    description: "Write one actionable task for the team.",
    placeholder: "fix login empty state",
    template: (input) => `Create one actionable implementation task: ${input || "the next useful improvement"}\nRequire code_patch and test or verification evidence.`,
  },
  {
    name: "/assign",
    title: "Assign work",
    description: "Route work to a role, repo, or person.",
    placeholder: "FE 민준 repo.ezmap-web login UI",
    template: (input) => `Assign this work with explicit routing: ${input || "the selected task"}\nMention provider, role, repo, workspace_ref, and required capabilities if known.`,
  },
  {
    name: "/run",
    title: "Queue run",
    description: "Prepare a proposal that can be confirmed into a worker command.",
    placeholder: "codex backend worker updates auth API",
    template: (input) => `Prepare this for execution as a Dipeen command proposal: ${input || "the ready task"}\nKeep risky side effects behind permission gates.`,
  },
  {
    name: "/review",
    title: "Review evidence",
    description: "Ask for evidence gaps and next verification.",
    placeholder: "latest worker result",
    template: (input) => `Review evidence for: ${input || "the latest run"}\nCall out missing artifacts, tests, receipts, or reasons this should not be DONE.`,
  },
  {
    name: "/approve",
    title: "Permission review",
    description: "Prepare approval context for a risky action.",
    placeholder: "git.commit for login fix",
    template: (input) => `Prepare permission review for: ${input || "the pending risky action"}\nSummarize target, risk, expected receipt, and why dry_run is enough unless explicitly escalated.`,
  },
  {
    name: "/invite",
    title: "Invite worker",
    description: "Explain the next worker onboarding command.",
    placeholder: "FE Codex worker for repo.ezmap-web",
    template: (input) => `Create worker onboarding instructions for: ${input || "a trusted teammate"}\nInclude role capabilities, local BYOK reminder, and the expected dipeen-agent join/start command shape.`,
  },
  {
    name: "/help",
    title: "Show commands",
    description: "Ask Dipeen to summarize available shortcuts.",
    placeholder: "",
    template: () => "Show the useful Dipeen slash commands and when to use them.",
  },
];

export const PROMPT_PRESETS = [
  {
    label: "Plan",
    value: "/plan current goal into small worker-routable tasks",
  },
  {
    label: "Assign",
    value: "/assign role.FE provider.codex repo.demo workspace.write",
  },
  {
    label: "Run",
    value: "/run selected proposal with evidence requirements",
  },
  {
    label: "Review",
    value: "/review latest artifacts and missing verification",
  },
];

export function expandSlashCommand(raw: string) {
  const text = raw.trim();
  if (!text.startsWith("/")) return text;
  const [name, ...rest] = text.split(/\s+/);
  const command = SLASH_COMMANDS.find((item) => item.name === name);
  if (!command) return text;
  return command.template(rest.join(" ").trim());
}

export function matchingSlashCommands(raw: string) {
  const text = raw.trimStart();
  if (!text.startsWith("/")) return [];
  const needle = text.split(/\s+/, 1)[0].toLowerCase();
  return SLASH_COMMANDS.filter((command) => command.name.startsWith(needle)).slice(0, 6);
}
