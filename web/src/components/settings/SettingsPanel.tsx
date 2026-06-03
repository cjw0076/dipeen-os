"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";
import {
  SpatialBadge,
  SpatialButton,
  SpatialIdentityMark,
  SpatialPanel,
  SpatialSegmentedControl,
} from "@/components/spatial/SpatialComponents";
import { dipeenNavItems, resolveDipeenNavHref } from "@/components/layout/dipeen-nav";
import { useAgents } from "@/hooks/useAgents";
import { useControlPlaneSummary } from "@/hooks/useControlPlaneSummary";
import { useUserProfile } from "@/hooks/useUserProfile";
import { useWorkspaceSpec } from "@/hooks/useWorkspaceSpec";
import { getApiBaseUrl } from "@/lib/api";

type SettingsSection = "workspace" | "providers" | "security" | "integrations" | "notifications" | "billing";
type ProviderKind = "cli" | "plugin" | "harness";
type ProviderStatus = "connected" | "needs_setup" | "waiting" | "offline";
type ToastState = { message: string; tone?: "ok" | "warn" | "danger" };

type ProviderRuntime = {
  id: string;
  label: string;
  model: string;
  kind: ProviderKind;
  status: ProviderStatus;
  endpoint: string;
  lastUsed: string;
  inspectCommand: string;
  detail: string;
  icon: BrandIconName;
};

const navItems = dipeenNavItems.filter((item) => item.label !== "BYOK Onboarding");

const sectionItems: Array<{ key: SettingsSection; label: string; icon: BrandIconName }> = [
  { key: "workspace", label: "Workspace", icon: "board" },
  { key: "providers", label: "Providers", icon: "workflow" },
  { key: "security", label: "Security", icon: "shield" },
  { key: "integrations", label: "Integrations", icon: "branch" },
  { key: "notifications", label: "Notifications", icon: "chat" },
  { key: "billing", label: "Billing", icon: "token" },
];

const providerOrder = ["claude", "codex", "omo", "omo-plugin", "hermes", "gemini"];

const providerBase: Record<string, Omit<ProviderRuntime, "status" | "lastUsed">> = {
  claude: {
    id: "claude",
    label: "Claude Code",
    model: "Claude local CLI",
    kind: "cli",
    endpoint: "local worker",
    inspectCommand: "dipeen providers inspect claude",
    detail: "Primary high-quality coding runtime. BYOK/subscription stays on worker.",
    icon: "code",
  },
  codex: {
    id: "codex",
    label: "Codex CLI",
    model: "Codex local CLI",
    kind: "cli",
    endpoint: "local worker",
    inspectCommand: "dipeen providers inspect codex",
    detail: "Developer runtime for code review, implementation, and local verification.",
    icon: "command",
  },
  omo: {
    id: "omo",
    label: "OMO CLI",
    model: "oh-my-opencode runtime",
    kind: "cli",
    endpoint: "worker adapter",
    inspectCommand: "dipeen providers probe omo",
    detail: "CLI harness for recursive edit/test loops. Capability is advertised only after probe passes.",
    icon: "workflow",
  },
  "omo-plugin": {
    id: "omo-plugin",
    label: "OMO Plugin",
    model: "event/artifact bridge",
    kind: "plugin",
    endpoint: "inbound adapter",
    inspectCommand: "dipeen providers render omo --format json",
    detail: "Plugin output is treated as inbound events and artifacts, never as source of truth.",
    icon: "layers",
  },
  hermes: {
    id: "hermes",
    label: "Hermes CLI",
    model: "memory/session harness",
    kind: "harness",
    endpoint: "worker adapter",
    inspectCommand: "dipeen providers probe hermes",
    detail: "CLI harness for memory candidates, skill candidates, context retrieval, and long-session summaries.",
    icon: "database",
  },
  gemini: {
    id: "gemini",
    label: "Gemini CLI",
    model: "Gemini local CLI",
    kind: "cli",
    endpoint: "optional worker",
    inspectCommand: "dipeen providers inspect gemini",
    detail: "Optional provider slot. Stays unadvertised until a healthy worker reports it.",
    icon: "spark",
  },
};

const integrationRows = [
  { id: "github", label: "GitHub", target: "repository and PR references", status: "connected", icon: "branch" as const },
  { id: "gitlab", label: "GitLab", target: "optional mirror", status: "waiting", icon: "branch" as const },
  { id: "slack", label: "Slack", target: "alerts and decision nudges", status: "connected", icon: "chat" as const },
  { id: "email", label: "Email / SMTP", target: "fallback notifications", status: "connected", icon: "review" as const },
];

const policyDefaults = [
  { id: "pr", label: "PR creation", caption: "Require review and checks", enabled: true },
  { id: "deploy", label: "Production deploy", caption: "Manual approval required", enabled: true },
  { id: "secret", label: "Secret access", caption: "Explicit approval and audit", enabled: true },
  { id: "merge", label: "Auto merge", caption: "Disabled by default", enabled: false },
];

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

function formatRelative(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 24 * 60) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / (24 * 60))}d ago`;
}

function statusTone(status?: string | null): "sage" | "honey" | "coral" | "slate" | "primary" {
  const raw = (status ?? "").toLowerCase();
  if (raw.includes("healthy") || raw.includes("connected") || raw.includes("online") || raw.includes("allowed")) return "sage";
  if (raw.includes("setup") || raw.includes("waiting") || raw.includes("pending")) return "honey";
  if (raw.includes("fail") || raw.includes("blocked") || raw.includes("offline") || raw.includes("denied")) return "coral";
  return "slate";
}

function StatusPill({ label }: { label: string }) {
  return <SpatialBadge tone={statusTone(label)}>{label}</SpatialBadge>;
}

function Toast({ toast }: { toast: ToastState }) {
  const tone = {
    ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
    warn: "border-amber-200 bg-amber-50 text-amber-800",
    danger: "border-red-200 bg-red-50 text-red-700",
  }[toast.tone ?? "ok"];
  return (
    <div className={cn("fixed bottom-5 right-5 z-50 rounded-lg border px-4 py-3 text-sm font-semibold shadow-[var(--ds-shadow-floating)]", tone)}>
      {toast.message}
    </div>
  );
}

function ShellSidebar({ roomId, workspaceName }: { roomId: string; workspaceName: string }) {
  return (
    <aside className="hidden h-screen w-[240px] shrink-0 flex-col border-r border-white/10 bg-[var(--ds-shell)] p-5 text-white lg:flex">
      <Link className="flex items-center gap-3" href="/app">
        <SpatialIdentityMark compact labelClassName="text-white" />
        <span className="text-xl font-bold">Dipeen</span>
      </Link>
      <nav className="mt-8 space-y-1">
        {navItems.map((item) => {
          const active = item.label === "Settings";
          return (
            <Link
              className={cn(
                "flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-semibold transition",
                active ? "bg-blue-600 text-white shadow-[0_16px_34px_rgba(37,99,235,0.34)]" : "text-slate-300 hover:bg-white/10 hover:text-white"
              )}
              href={resolveDipeenNavHref(item, roomId)}
              key={item.label}
            >
              <BrandIcon name={item.icon} size={17} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto rounded-xl border border-white/10 bg-white/[0.06] p-3">
        <div className="flex items-center gap-3">
          <img alt="" className="size-10 rounded-full object-cover ring-1 ring-white/20" src="/assets/agents/human-manager.png" />
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-white">{workspaceName}</p>
            <p className="text-xs text-slate-400">admin</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

function TopBar({
  workspaceName,
  locale,
  onLocale,
  snapshotAt,
}: {
  workspaceName: string;
  locale: "EN" | "KO";
  onLocale: (locale: "EN" | "KO") => void;
  snapshotAt?: string | null;
}) {
  return (
    <header className="sticky top-0 z-20 flex min-h-[72px] items-center justify-between gap-4 border-b border-[var(--ds-border)] bg-white/90 px-5 backdrop-blur-xl">
      <div className="flex min-w-0 items-center gap-5">
        <button className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[var(--ds-border)] bg-white px-3 text-sm font-bold text-[var(--ds-text)] shadow-sm" type="button">
          <BrandIcon className="text-[var(--ds-primary)]" name="board" size={16} />
          <span className="truncate">{workspaceName}</span>
        </button>
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-[var(--ds-text)]">Settings / Providers</h1>
          <p className="mt-1 text-sm text-[var(--ds-text-muted)]">Configure providers, security, policies, and workspace runtime boundaries.</p>
        </div>
      </div>
      <div className="hidden items-center gap-3 md:flex">
        <span className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-emerald-200 bg-white px-3 text-xs font-bold text-emerald-700 shadow-sm">
          <span className="size-2 rounded-full bg-emerald-500" />
          All Systems Operational
        </span>
        <Link className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-[var(--ds-border)] bg-white px-3 text-xs font-bold text-[var(--ds-text)] shadow-sm" href="/flow">
          <BrandIcon name="review" size={15} />
          Docs
        </Link>
        <button className="relative grid size-9 place-items-center rounded-lg border border-[var(--ds-border)] bg-white text-[var(--ds-text-muted)] shadow-sm" type="button">
          <BrandIcon name="chat" size={16} />
          <span className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-red-500 text-[10px] font-bold text-white">3</span>
        </button>
        <SpatialSegmentedControl
          items={[
            { label: "EN", active: locale === "EN", onClick: () => onLocale("EN") },
            { label: "KO", active: locale === "KO", onClick: () => onLocale("KO") },
          ]}
        />
        <span className="text-xs text-[var(--ds-text-subtle)]">{snapshotAt ? formatTime(snapshotAt) : "Live"}</span>
        <img alt="" className="size-10 rounded-full object-cover ring-1 ring-[var(--ds-border)]" src="/assets/agents/human-manager.png" />
      </div>
    </header>
  );
}

function SectionTabs({ active, onChange }: { active: SettingsSection; onChange: (section: SettingsSection) => void }) {
  return (
    <div className="grid overflow-hidden rounded-lg border border-[var(--ds-border)] bg-white shadow-sm sm:grid-cols-2 xl:grid-cols-6">
      {sectionItems.map((item) => (
        <button
          className={cn(
            "inline-flex min-h-11 items-center justify-center gap-2 border-b border-[var(--ds-border)] px-3 text-sm font-bold transition sm:border-r xl:border-b-0",
            active === item.key ? "bg-[var(--ds-primary-soft)] text-[var(--ds-primary)] shadow-[inset_0_-2px_0_var(--ds-primary)]" : "text-[var(--ds-text-muted)] hover:bg-[var(--ds-bg-muted)] hover:text-[var(--ds-text)]"
          )}
          key={item.key}
          onClick={() => onChange(item.key)}
          type="button"
        >
          <BrandIcon name={item.icon} size={16} />
          {item.label}
        </button>
      ))}
    </div>
  );
}

function ProviderLogo({ runtime }: { runtime: ProviderRuntime }) {
  const style = runtime.kind === "plugin" ? "bg-violet-50 text-violet-700 ring-violet-200" : runtime.kind === "harness" ? "bg-blue-50 text-blue-700 ring-blue-200" : "bg-slate-950 text-white ring-slate-200";
  return (
    <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg ring-1", style)}>
      <BrandIcon name={runtime.icon} size={18} />
    </span>
  );
}

function ProviderRuntimeMatrix({
  providers,
  selectedId,
  onSelect,
  onCopy,
}: {
  providers: ProviderRuntime[];
  selectedId: string;
  onSelect: (id: string) => void;
  onCopy: (command: string) => void;
}) {
  return (
    <SpatialPanel
      action={<SpatialButton icon="workflow" onClick={() => onCopy("dipeen providers inspect all")} variant="secondary">Inspect all</SpatialButton>}
      className="p-0"
      description="Manage LLM/runtime providers used by local workers."
      icon="workflow"
      title="Provider Runtime Matrix"
    >
      <div className="overflow-x-auto">
        <table className="min-w-[760px] w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--ds-border)] text-xs font-bold text-[var(--ds-text-muted)]">
              <th className="px-5 py-3">Provider</th>
              <th className="px-4 py-3">Model / Runtime</th>
              <th className="px-4 py-3">Kind</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Endpoint</th>
              <th className="px-4 py-3">Last Used</th>
              <th className="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((runtime) => (
              <tr
                className={cn(
                  "border-b border-[var(--ds-border)] transition last:border-0 hover:bg-[var(--ds-bg-muted)]",
                  selectedId === runtime.id && "bg-[var(--ds-primary-soft)]/55"
                )}
                key={runtime.id}
              >
                <td className="px-5 py-3">
                  <button className="flex min-w-0 items-center gap-3 text-left" onClick={() => onSelect(runtime.id)} type="button">
                    <ProviderLogo runtime={runtime} />
                    <span className="min-w-0">
                      <span className="block truncate font-bold text-[var(--ds-text)]">{runtime.label}</span>
                      <span className="block truncate text-xs text-[var(--ds-text-muted)]">{runtime.detail}</span>
                    </span>
                  </button>
                </td>
                <td className="px-4 py-3 text-[var(--ds-text-muted)]">{runtime.model}</td>
                <td className="px-4 py-3">
                  <SpatialBadge tone={runtime.kind === "plugin" ? "violet" : runtime.kind === "harness" ? "primary" : "slate"}>{runtime.kind}</SpatialBadge>
                </td>
                <td className="px-4 py-3"><StatusPill label={runtime.status.replace("_", " ")} /></td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--ds-text-muted)]">{runtime.endpoint}</td>
                <td className="px-4 py-3 text-[var(--ds-text-muted)]">{runtime.lastUsed}</td>
                <td className="px-5 py-3">
                  <div className="flex justify-end gap-2">
                    <button className="rounded-md border border-[var(--ds-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--ds-text)] hover:border-[var(--ds-primary)]" onClick={() => onSelect(runtime.id)} type="button">
                      Configure
                    </button>
                    <button className="grid size-8 place-items-center rounded-md text-[var(--ds-text-muted)] hover:bg-white hover:text-[var(--ds-primary)]" onClick={() => onCopy(runtime.inspectCommand)} type="button">
                      <BrandIcon name="inspect" size={15} title={`Copy ${runtime.label} command`} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--ds-border)] px-5 py-4">
        <button className="inline-flex min-h-9 items-center gap-2 rounded-md border border-[var(--ds-border)] bg-white px-3 text-sm font-bold text-[var(--ds-text-muted)] hover:text-[var(--ds-primary)]" type="button">
          <BrandIcon name="workflow" size={15} />
          Add Provider
        </button>
        <button className="text-sm font-bold text-[var(--ds-primary)]" onClick={() => onCopy("dipeen providers render all --format json")} type="button">
          View provider usage
        </button>
      </footer>
    </SpatialPanel>
  );
}

function ProviderInspector({ runtime, onCopy }: { runtime: ProviderRuntime; onCopy: (command: string) => void }) {
  return (
    <SpatialPanel className="p-0" description="Provider output is translated into canonical Dipeen resources." icon="inspect" title="Provider Inspector">
      <div className="space-y-4 p-5">
        <div className="flex items-start gap-3">
          <ProviderLogo runtime={runtime} />
          <div className="min-w-0 flex-1">
            <p className="text-base font-bold text-[var(--ds-text)]">{runtime.label}</p>
            <p className="mt-1 text-sm leading-6 text-[var(--ds-text-muted)]">{runtime.detail}</p>
          </div>
          <StatusPill label={runtime.status.replace("_", " ")} />
        </div>
        <div className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-bg-muted)] p-3">
          <p className="text-xs font-bold uppercase text-[var(--ds-text-muted)]">Local command</p>
          <code className="mt-2 block break-all rounded-md bg-white px-3 py-2 text-xs text-[var(--ds-text)] ring-1 ring-[var(--ds-border)]">{runtime.inspectCommand}</code>
          <button className="mt-3 text-sm font-bold text-[var(--ds-primary)]" onClick={() => onCopy(runtime.inspectCommand)} type="button">Copy command</button>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-white p-3 ring-1 ring-[var(--ds-border)]">
            <p className="text-xs text-[var(--ds-text-muted)]">Type</p>
            <p className="mt-1 font-bold text-[var(--ds-text)]">{runtime.kind}</p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-[var(--ds-border)]">
            <p className="text-xs text-[var(--ds-text-muted)]">Endpoint</p>
            <p className="mt-1 truncate font-bold text-[var(--ds-text)]">{runtime.endpoint}</p>
          </div>
          <div className="rounded-lg bg-white p-3 ring-1 ring-[var(--ds-border)]">
            <p className="text-xs text-[var(--ds-text-muted)]">Trust</p>
            <p className="mt-1 font-bold text-[var(--ds-text)]">verified by Dipeen</p>
          </div>
        </div>
      </div>
    </SpatialPanel>
  );
}

function ByokPanel({ onCopy }: { onCopy: (command: string) => void }) {
  const hasAnthropic = typeof window !== "undefined" && Boolean(localStorage.getItem("dipeen_anthropic_key"));
  const hasOpenAI = typeof window !== "undefined" && Boolean(localStorage.getItem("dipeen_openai_key"));
  const status = hasAnthropic || hasOpenAI ? "configured" : "local only";
  return (
    <SpatialPanel className="p-0" description="Keys are stored on worker machines and never leave your environment." icon="key" title="Bring Your Own Key (BYOK)">
      <div className="divide-y divide-[var(--ds-border)]">
        {[
          ["Key Status", status],
          ["Key ID", hasAnthropic ? "anthropic local credential" : hasOpenAI ? "openai local credential" : "not transmitted"],
          ["Storage", "Local keychain / worker env"],
          ["Last Verified", "via provider probe"],
        ].map(([label, value]) => (
          <div className="grid grid-cols-[120px_1fr_auto] items-center gap-3 px-5 py-3 text-sm" key={label}>
            <span className="font-semibold text-[var(--ds-text-muted)]">{label}</span>
            <span className="truncate text-[var(--ds-text)]">{value}</span>
            {label === "Last Verified" && (
              <button className="rounded-md border border-[var(--ds-border)] px-3 py-1 text-xs font-bold text-[var(--ds-text-muted)] hover:text-[var(--ds-primary)]" onClick={() => onCopy("dipeen providers probe hermes")} type="button">Verify</button>
            )}
          </div>
        ))}
      </div>
      <div className="p-5">
        <div className="inline-flex items-center gap-2 rounded-lg bg-[var(--ds-sage-soft)] px-3 py-2 text-sm font-bold text-[var(--ds-sage)]">
          <BrandIcon name="check" size={16} />
          Server receives no provider keys.
        </div>
      </div>
    </SpatialPanel>
  );
}

function TunnelPanel({ onCopy }: { onCopy: (command: string) => void }) {
  const rows = [
    ["Tunnel ID", "workspace tunnel"],
    ["Edge Location", "Cloudflare auto"],
    ["Tunnel Health", "healthy"],
    ["Outbound 443/HTTPS", "allowed"],
    ["NAT Detection", "open by worker pull"],
  ];
  return (
    <SpatialPanel className="p-0" description="Worker nodes connect outward, so no router port-forwarding is required." icon="workflow" title="Cloudflare Tunnel & NAT">
      <div className="divide-y divide-[var(--ds-border)]">
        {rows.map(([label, value]) => (
          <div className="flex items-center justify-between gap-3 px-5 py-3 text-sm" key={label}>
            <span className="font-semibold text-[var(--ds-text-muted)]">{label}</span>
            <span className="text-right font-medium text-[var(--ds-text)]">{value}</span>
          </div>
        ))}
      </div>
      <div className="p-5">
        <SpatialButton icon="workflow" onClick={() => onCopy("dipeen hq expose")} variant="secondary">Manage Tunnel</SpatialButton>
      </div>
    </SpatialPanel>
  );
}

function TeamRolesPanel({ agents }: { agents: ReturnType<typeof useAgents>["agents"] }) {
  const rows = agents.length
    ? agents.slice(0, 5).map((agent) => ({
        id: agent.agent_id,
        label: agent.label,
        role: agent.role ?? "member",
        status: agent.status,
      }))
    : [
        { id: "frontend", label: "Frontend Worker", role: "FE", status: "waiting" },
        { id: "backend", label: "Backend Worker", role: "BE", status: "waiting" },
        { id: "qa", label: "QA Worker", role: "QA", status: "waiting" },
      ];

  return (
    <SpatialPanel
      action={<button className="text-xs font-bold text-[var(--ds-primary)]" type="button">Invite Member</button>}
      className="p-0"
      description="Manage members and runtime roles."
      icon="agent"
      title="Team & Roles"
    >
      <div className="divide-y divide-[var(--ds-border)]">
        {rows.map((row, index) => (
          <div className="flex items-center gap-3 px-5 py-3" key={row.id}>
            <img
              alt=""
              className="size-9 rounded-full object-cover ring-1 ring-[var(--ds-border)]"
              src={["/assets/agents/human-manager.png", "/assets/agents/fe-agent.png", "/assets/agents/be-agent.png", "/assets/agents/qa-agent.png", "/assets/agents/pm-agent.png"][index % 5]}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-[var(--ds-text)]">{row.label}</p>
              <p className="truncate text-xs text-[var(--ds-text-muted)]">{row.status}</p>
            </div>
            <SpatialBadge tone={row.role.toLowerCase().includes("qa") ? "violet" : row.role.toLowerCase().includes("be") ? "sage" : "primary"}>{row.role}</SpatialBadge>
          </div>
        ))}
      </div>
      <div className="px-5 py-4">
        <Link className="text-sm font-bold text-[var(--ds-primary)]" href="/onboarding">View all members and roles</Link>
      </div>
    </SpatialPanel>
  );
}

function SystemHealthPanel({ items }: { items: Array<{ id: string; label: string; status: string; detail: string }> }) {
  const rows = items.length
    ? items.slice(0, 6)
    : [
        { id: "dipeen-core", label: "Dipeen Core", status: "healthy", detail: "API reachable" },
        { id: "agent-runtimes", label: "Agent Runtimes", status: "waiting", detail: "probe required" },
        { id: "providers", label: "Providers", status: "waiting", detail: "capability pending" },
        { id: "event-stream", label: "Event Stream", status: "healthy", detail: "ready" },
      ];
  return (
    <SpatialPanel className="p-0" description="Control-plane readiness." icon="check" title="System Health">
      <div className="divide-y divide-[var(--ds-border)]">
        {rows.map((item) => (
          <div className="grid grid-cols-[auto_1fr_auto] items-center gap-3 px-5 py-3" key={item.id}>
            <BrandIcon className="text-[var(--ds-primary)]" name="check" size={17} />
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-[var(--ds-text)]">{item.label}</p>
              <p className="truncate text-xs text-[var(--ds-text-muted)]">{item.detail}</p>
            </div>
            <StatusPill label={item.status} />
          </div>
        ))}
      </div>
      <div className="px-5 py-4">
        <Link className="text-sm font-bold text-[var(--ds-primary)]" href="/app">View system status</Link>
      </div>
    </SpatialPanel>
  );
}

function PolicyEnginePanel({ onChange }: { onChange: (message: string) => void }) {
  const [policies, setPolicies] = useState(policyDefaults);
  const toggle = (id: string) => {
    setPolicies((prev) => prev.map((policy) => policy.id === id ? { ...policy, enabled: !policy.enabled } : policy));
    onChange("Policy state updated locally");
  };
  return (
    <SpatialPanel className="p-0" description="Guardrails and automation policies." icon="shield" title="Policy Engine">
      <div className="divide-y divide-[var(--ds-border)]">
        {policies.map((policy) => (
          <div className="grid grid-cols-[1fr_auto] items-center gap-4 px-5 py-3" key={policy.id}>
            <div>
              <p className="text-sm font-bold text-[var(--ds-text)]">{policy.label}</p>
              <p className="text-xs text-[var(--ds-text-muted)]">{policy.caption}</p>
            </div>
            <button
              aria-pressed={policy.enabled}
              className={cn(
                "relative h-7 w-12 rounded-full transition",
                policy.enabled ? "bg-[var(--ds-primary)]" : "bg-slate-300"
              )}
              onClick={() => toggle(policy.id)}
              type="button"
            >
              <span className={cn("absolute top-1 size-5 rounded-full bg-white shadow transition", policy.enabled ? "left-6" : "left-1")} />
            </button>
          </div>
        ))}
      </div>
      <div className="px-5 py-4">
        <button className="text-sm font-bold text-[var(--ds-primary)]" onClick={() => onChange("Policy editor is ready for wiring")} type="button">Edit policies</button>
      </div>
    </SpatialPanel>
  );
}

function IntegrationsPanel() {
  return (
    <SpatialPanel className="p-0" description="Connect external systems and receive events." icon="branch" title="Integrations">
      <div className="divide-y divide-[var(--ds-border)]">
        {integrationRows.map((row) => (
          <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-5 py-3" key={row.id}>
            <BrandIcon className="text-[var(--ds-text)]" name={row.icon} size={21} />
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-[var(--ds-text)]">{row.label}</p>
              <p className="truncate text-xs text-[var(--ds-text-muted)]">{row.target}</p>
            </div>
            <StatusPill label={row.status} />
            <button className="grid size-8 place-items-center rounded-md text-[var(--ds-text-muted)] hover:bg-[var(--ds-bg-muted)] hover:text-[var(--ds-primary)]" type="button">
              <BrandIcon name="settings" size={15} />
            </button>
          </div>
        ))}
      </div>
      <div className="px-5 py-4">
        <button className="text-sm font-bold text-[var(--ds-primary)]" type="button">Manage integrations</button>
      </div>
    </SpatialPanel>
  );
}

function AuditPanel({ events }: { events: Array<{ event_id: string; event_type: string; producer: string; created_at: string; message: string }> }) {
  const rows = events.length
    ? events.slice(0, 5)
    : [
        { event_id: "audit-1", event_type: "workspace.ready", producer: "dipeen://core", created_at: new Date().toISOString(), message: "Workspace policy loaded" },
      ];
  return (
    <SpatialPanel className="p-0" description="Latest provider and policy activity." icon="inspect" title="Audit Log">
      <div className="divide-y divide-[var(--ds-border)]">
        {rows.map((event) => (
          <div className="grid grid-cols-[70px_1fr_auto] items-center gap-3 px-5 py-2.5 text-sm" key={event.event_id}>
            <span className="text-xs text-[var(--ds-text-muted)]">{formatTime(event.created_at)}</span>
            <div className="min-w-0">
              <p className="truncate font-semibold text-[var(--ds-text)]">{event.message || event.event_type}</p>
              <p className="truncate text-xs text-[var(--ds-text-muted)]">{event.producer}</p>
            </div>
            <BrandIcon className="text-[var(--ds-text-subtle)]" name="inspect" size={15} />
          </div>
        ))}
      </div>
      <div className="px-5 py-4">
        <Link className="text-sm font-bold text-[var(--ds-primary)]" href="/dashboard">View full audit log</Link>
      </div>
    </SpatialPanel>
  );
}

function WorkspaceDetailsPanel({
  workspaceId,
  mode,
  repoCount,
  apiBase,
}: {
  workspaceId: string;
  mode: string;
  repoCount: number;
  apiBase: string;
}) {
  const details = [
    ["Workspace ID", workspaceId],
    ["Mode", mode],
    ["Repos", `${repoCount}`],
    ["API URL", apiBase],
  ];
  return (
    <SpatialPanel
      action={<SpatialButton icon="settings" variant="secondary">Edit Workspace</SpatialButton>}
      className="p-0"
      icon="board"
      title="Workspace Details"
    >
      <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
        {details.map(([label, value]) => (
          <div key={label}>
            <p className="text-xs font-bold text-[var(--ds-text-muted)]">{label}</p>
            <p className="mt-1 truncate text-sm font-semibold text-[var(--ds-text)]">{value}</p>
          </div>
        ))}
      </div>
    </SpatialPanel>
  );
}

function DataBoundaryPanel() {
  return (
    <SpatialPanel className="border-blue-200 bg-blue-50/50 p-0" description="Dipeen gates and observes. Workers execute locally." icon="shield" title="Data Boundary & Retention">
      <div className="grid gap-4 p-5 sm:grid-cols-[1fr_auto]">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <p className="text-xs font-bold text-[var(--ds-text-muted)]">Data Boundary</p>
            <p className="mt-1 text-sm font-bold text-[var(--ds-text)]">Provider keys stay local</p>
          </div>
          <div>
            <p className="text-xs font-bold text-[var(--ds-text-muted)]">Retention Policy</p>
            <p className="mt-1 text-sm font-bold text-[var(--ds-text)]">Configurable by workspace</p>
          </div>
        </div>
        <div className="grid size-20 place-items-center rounded-2xl bg-white text-[var(--ds-primary)] shadow-[var(--ds-shadow-card)]">
          <BrandIcon name="shield" size={34} />
        </div>
      </div>
    </SpatialPanel>
  );
}

function DangerZonePanel({ onAction }: { onAction: (label: string) => void }) {
  return (
    <SpatialPanel className="border-red-200 bg-red-50/45 p-0" description="These actions require explicit confirmation." icon="shield" title="Danger Zone">
      <div className="space-y-2 p-5">
        {["Revoke All Agent Tokens", "Reset Workspace", "Delete Workspace"].map((label) => (
          <button
            className="flex min-h-11 w-full items-center gap-3 rounded-lg border border-red-200 bg-white px-3 text-sm font-bold text-red-600 transition hover:bg-red-50"
            key={label}
            onClick={() => onAction(`${label} requires a separate confirmation flow`)}
            type="button"
          >
            <BrandIcon name="shield" size={16} />
            {label}
          </button>
        ))}
      </div>
    </SpatialPanel>
  );
}

export function SettingsPanel() {
  const { name } = useUserProfile();
  const { agents } = useAgents();
  const { summary, error: summaryError } = useControlPlaneSummary();
  const { spec, error: specError } = useWorkspaceSpec();
  const [activeSection, setActiveSection] = useState<SettingsSection>("providers");
  const [locale, setLocale] = useState<"EN" | "KO">("EN");
  const [selectedProviderId, setSelectedProviderId] = useState("claude");
  const [toast, setToast] = useState<ToastState | null>(null);

  const showToast = useCallback((message: string, tone: ToastState["tone"] = "ok") => {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 2400);
  }, []);

  const copyText = useCallback((text: string) => {
    void navigator.clipboard?.writeText(text).then(
      () => showToast("Copied command"),
      () => showToast("Copy failed", "warn")
    );
  }, [showToast]);

  const providerRows = useMemo<ProviderRuntime[]>(() => {
    const live = new Map((summary?.providers ?? []).map((provider) => [provider.id.toLowerCase(), provider]));
    const specProviders = spec?.providers ?? {};
    return providerOrder.map((id) => {
      const base = providerBase[id];
      const liveProvider = live.get(id) ?? live.get(base.label.toLowerCase()) ?? live.get(id.replace("-plugin", ""));
      const inSpec = Object.prototype.hasOwnProperty.call(specProviders, id.replace("-plugin", ""));
      const status: ProviderStatus = liveProvider?.healthy
        ? "connected"
        : id === "omo-plugin"
          ? "waiting"
          : inSpec || id === "gemini"
            ? "needs_setup"
            : "offline";
      return {
        ...base,
        status,
        lastUsed: liveProvider?.last_heartbeat ? formatRelative(liveProvider.last_heartbeat) : status === "connected" ? "recent" : "-",
      };
    });
  }, [spec?.providers, summary?.providers]);

  const selectedProvider = providerRows.find((provider) => provider.id === selectedProviderId) ?? providerRows[0];
  const workspaceName = spec?.workspace_id ?? name ?? "Dipeen Workspace";
  const activeRoomId = "general";
  const apiBase = getApiBaseUrl();
  const providerCount = providerRows.filter((provider) => provider.status === "connected").length;
  const waitingCount = providerRows.filter((provider) => provider.status === "needs_setup" || provider.status === "waiting").length;
  const systemHealth = summary?.system_health ?? [];

  return (
    <div className="dp-app" data-dipeen-locale={locale.toLowerCase()} data-dipeen-theme="light">
      {toast && <Toast toast={toast} />}
      <ShellSidebar roomId={activeRoomId} workspaceName={workspaceName} />
      <main className="dp-page-main overflow-auto">
        <TopBar
          locale={locale}
          onLocale={setLocale}
          snapshotAt={summary?.snapshot_at}
          workspaceName={workspaceName}
        />
        <div className="space-y-4 p-5">
          {(summaryError || specError) && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
              {summaryError ? `Control-plane API: ${summaryError}` : `Workspace spec API: ${specError}`}
            </div>
          )}

          <SectionTabs active={activeSection} onChange={setActiveSection} />

          <section className="grid gap-4 xl:grid-cols-[1fr_420px]">
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <SpatialPanel className="p-4">
                  <p className="text-xs font-bold text-[var(--ds-text-muted)]">Connected providers</p>
                  <p className="mt-2 text-3xl font-bold text-[var(--ds-primary)]">{providerCount}</p>
                  <p className="mt-1 text-xs text-[var(--ds-text-subtle)]">{providerRows.length} registered slots</p>
                </SpatialPanel>
                <SpatialPanel className="p-4">
                  <p className="text-xs font-bold text-[var(--ds-text-muted)]">Needs setup</p>
                  <p className="mt-2 text-3xl font-bold text-[var(--ds-honey)]">{waitingCount}</p>
                  <p className="mt-1 text-xs text-[var(--ds-text-subtle)]">probe before capability advertise</p>
                </SpatialPanel>
                <SpatialPanel className="p-4">
                  <p className="text-xs font-bold text-[var(--ds-text-muted)]">Executor mode</p>
                  <p className="mt-2 text-2xl font-bold text-[var(--ds-sage)]">{spec?.policies["permission_executor_mode"] ?? "dry_run"}</p>
                  <p className="mt-1 text-xs text-[var(--ds-text-subtle)]">no PR, push, or deploy by default</p>
                </SpatialPanel>
              </div>

              {(activeSection === "providers" || activeSection === "workspace") && (
                <ProviderRuntimeMatrix
                  onCopy={copyText}
                  onSelect={setSelectedProviderId}
                  providers={providerRows}
                  selectedId={selectedProvider.id}
                />
              )}

              {(activeSection === "security" || activeSection === "workspace") && (
                <div className="grid gap-4 xl:grid-cols-2">
                  <PolicyEnginePanel onChange={(message) => showToast(message, "warn")} />
                  <IntegrationsPanel />
                </div>
              )}

              {activeSection === "integrations" && <IntegrationsPanel />}
              {activeSection === "notifications" && (
                <SpatialPanel className="p-5" description="Route decision nudges to the right surface." icon="chat" title="Notifications">
                  <div className="grid gap-3 md:grid-cols-3">
                    {["Permission nudges", "Worker failures", "Memory candidates"].map((label) => (
                      <div className="rounded-lg border border-[var(--ds-border)] bg-white p-4" key={label}>
                        <p className="text-sm font-bold text-[var(--ds-text)]">{label}</p>
                        <p className="mt-1 text-xs text-[var(--ds-text-muted)]">Enabled for web inbox and audit trail.</p>
                      </div>
                    ))}
                  </div>
                </SpatialPanel>
              )}
              {activeSection === "billing" && (
                <SpatialPanel className="p-5" description="Usage is visible, provider billing remains outside Dipeen." icon="token" title="Billing & Usage Boundary">
                  <p className="text-sm leading-6 text-[var(--ds-text-muted)]">
                    Dipeen tracks token and run evidence for the workspace, but provider subscription, BYOK billing, and local credentials stay with each worker/provider account.
                  </p>
                </SpatialPanel>
              )}

              <WorkspaceDetailsPanel
                apiBase={apiBase}
                mode={spec?.mode ?? "team"}
                repoCount={spec?.project.repos.length ?? 0}
                workspaceId={workspaceName}
              />
            </div>

            <aside className="space-y-4">
              <ByokPanel onCopy={copyText} />
              <TunnelPanel onCopy={copyText} />
              <ProviderInspector onCopy={copyText} runtime={selectedProvider} />
              <TeamRolesPanel agents={agents} />
              <SystemHealthPanel items={systemHealth} />
              <AuditPanel events={summary?.latest_events ?? []} />
              <DataBoundaryPanel />
              <DangerZonePanel onAction={(message) => showToast(message, "danger")} />
            </aside>
          </section>
        </div>
      </main>
    </div>
  );
}
