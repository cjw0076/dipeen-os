"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAgents } from "@/hooks/useAgents";
import { useAgentPanel } from "@/contexts/AgentPanelContext";
import { auth } from "@/lib/auth";

const NAV = [
  { href: "/", label: "Control", icon: "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" },
  { href: "/meeting/general", label: "Meeting", icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" },
  { href: "/office", label: "Office", icon: "M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" },
  { href: "/graph", label: "Graph", icon: "M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" },
  { href: "/dashboard", label: "Runs", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" },
  { href: "/onboarding", label: "Setup", icon: "M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l3 3m0 0l-3 3m3-3H3" },
  { href: "/settings", label: "Settings", icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" },
];

function NavIcon({ d }: { d: string }) {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    working: "bg-status-working",
    idle: "bg-status-idle",
    done: "bg-status-done",
    error: "bg-status-error",
    offline: "bg-zinc-700",
  };
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      {status === "working" && (
        <span className="absolute inline-flex h-full w-full rounded-full bg-status-working opacity-75 animate-ping" />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${colors[status] ?? "bg-zinc-700"}`} />
    </span>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const { agents: liveAgents } = useAgents();
  const { openAgentPanel } = useAgentPanel();

  const agents = liveAgents;

  return (
    <aside className={`${collapsed ? "w-14" : "w-52"} h-full bg-bg-secondary border-r border-border-subtle flex flex-col transition-all duration-200 shrink-0`}>
      {/* Header */}
      <div className="h-12 flex items-center px-3 border-b border-border-subtle gap-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-7 h-7 rounded-md bg-accent flex items-center justify-center text-white text-xs font-bold hover:bg-accent-hover transition-colors shrink-0"
        >
          d
        </button>
        {!collapsed && (
          <span className="text-sm font-semibold tracking-tight">dipeen</span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-2 px-1.5 space-y-0.5 overflow-y-auto">
        {NAV.map((item) => {
          const active = item.href.startsWith("/meeting")
            ? pathname.startsWith("/meeting")
            : pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                active
                  ? "bg-bg-hover text-text-primary"
                  : "text-text-secondary hover:bg-bg-hover/50 hover:text-text-primary"
              }`}
              title={collapsed ? item.label : undefined}
            >
              <NavIcon d={item.icon} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}

        {/* Agents section */}
        {!collapsed && (
          <div className="pt-4">
            <p className="px-2.5 pb-1.5 text-[11px] font-medium text-text-muted uppercase tracking-widest">
              Agents
            </p>
            {agents.map((agent) => (
              <div
                key={agent.agent_id}
                onClick={() => openAgentPanel(agent.agent_id, agent.label)}
                className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] text-text-secondary hover:bg-bg-hover/50 transition-colors cursor-pointer group"
              >
                <StatusDot status={agent.status} />
                <span
                  className="w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center text-black/80 shrink-0"
                  style={{ backgroundColor: agent.color }}
                >
                  {agent.role}
                </span>
                <span className="truncate group-hover:text-text-primary transition-colors">
                  {agent.label}
                </span>
              </div>
            ))}
          </div>
        )}
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-border-subtle shrink-0 space-y-0.5">
        <button
          className="w-full px-2.5 py-1.5 rounded-md text-[11px] text-text-muted hover:text-text-secondary hover:bg-bg-hover/50 transition-colors text-left"
          onClick={() => document.documentElement.classList.toggle("light")}
        >
          {collapsed ? "◐" : "◐ Toggle theme"}
        </button>
        {auth.isAuthenticated() && (
          <button
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[11px] text-text-muted hover:text-status-error hover:bg-status-error/10 transition-colors text-left"
            onClick={() => auth.logout()}
            title="Sign out"
          >
            <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            {!collapsed && <span>Sign out</span>}
          </button>
        )}
      </div>
    </aside>
  );
}
