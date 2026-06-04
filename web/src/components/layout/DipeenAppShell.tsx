"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { dipeenNavItems, resolveDipeenNavHref } from "@/components/layout/dipeen-nav";
import { SpatialIdentityMark, SpatialSegmentedControl } from "@/components/spatial/SpatialComponents";
import { BrandIcon } from "@/components/ui/brand-icons";

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type Locale = "EN" | "KO";

type DipeenAppShellProps = {
  activeLabels?: string[];
  children: ReactNode;
  eyebrow?: string;
  footerAvatarSrc?: string;
  footerCaption?: string;
  footerLabel?: string;
  locale?: Locale;
  onLocale?: (locale: Locale) => void;
  right?: ReactNode;
  roomId?: string;
  subtitle?: string;
  title: string;
  visibleNavLabels?: string[];
  workspaceName?: string;
};

const hiddenSidebarLabels = new Set(["BYOK Onboarding"]);

function isRouteActive({
  activeLabels,
  href,
  label,
  pathname,
}: {
  activeLabels?: string[];
  href: string;
  label: string;
  pathname: string;
}) {
  if (activeLabels?.includes(label)) return true;
  if (activeLabels?.length) return false;
  if (label === "Overview") return pathname === "/app" || pathname === "/";
  if (href !== "/app" && pathname.startsWith(href)) return true;
  return pathname === href;
}

export function DipeenAppShell({
  activeLabels,
  children,
  eyebrow = "Dipeen Control Tower",
  footerAvatarSrc = "/assets/agents/human-manager.png",
  footerCaption = "control-plane user",
  footerLabel,
  locale,
  onLocale,
  right,
  roomId,
  subtitle,
  title,
  visibleNavLabels,
  workspaceName = "Dipeen Workspace",
}: DipeenAppShellProps) {
  const pathname = usePathname();
  const visibleNav = new Set(visibleNavLabels);
  const navItems = dipeenNavItems.filter((item) => {
    if (hiddenSidebarLabels.has(item.label)) return false;
    return visibleNavLabels ? visibleNav.has(item.label) : true;
  });

  return (
    <div className="dp-app" data-dipeen-locale={locale?.toLowerCase()} data-dipeen-theme="light">
      <aside className="dp-sidebar hidden h-screen flex-col lg:flex">
        <Link className="flex items-center gap-3" href="/app">
          <SpatialIdentityMark compact labelClassName="text-white" />
          <span className="text-lg font-bold tracking-tight text-white">Dipeen</span>
        </Link>
        <nav className="mt-7 space-y-1">
          {navItems.map((item) => {
            const href = resolveDipeenNavHref(item, roomId);
            const active = isRouteActive({ activeLabels, href, label: item.label, pathname });
            return (
              <Link
                className={cn(
                  "flex min-h-10 items-center gap-3 rounded-lg px-3 text-[13px] font-semibold transition",
                  active ? "dp-active" : "text-slate-300 hover:bg-white/[0.08] hover:text-white",
                )}
                href={href}
                key={item.label}
              >
                <BrandIcon name={item.icon} size={16} />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto rounded-lg border border-white/10 bg-white/[0.06] p-3">
          <div className="flex items-center gap-3">
            <img alt="" className="size-10 rounded-full object-cover ring-1 ring-white/20" src={footerAvatarSrc} />
            <div className="min-w-0">
              <p className="truncate text-[12px] font-bold text-white">{footerLabel ?? workspaceName}</p>
              <p className="mt-0.5 truncate text-[11px] text-slate-400">{footerCaption}</p>
            </div>
          </div>
        </div>
      </aside>

      <main className="dp-page-main overflow-auto">
        <header className="dp-topbar sticky top-0 z-20 flex flex-col justify-center gap-3 px-4 py-3 lg:px-6">
          <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <p className="text-[12px] font-bold text-[var(--ds-primary)]">{eyebrow}</p>
              <h1 className="mt-1 truncate text-xl font-bold text-[var(--ds-text)]">{title}</h1>
              {subtitle && <p className="mt-1 max-w-3xl truncate text-xs font-medium text-[var(--ds-text-muted)]">{subtitle}</p>}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-3 text-xs text-[var(--ds-text-muted)]">
              {locale && onLocale && (
                <SpatialSegmentedControl
                  items={[
                    { label: "EN", active: locale === "EN", onClick: () => onLocale("EN") },
                    { label: "KO", active: locale === "KO", onClick: () => onLocale("KO") },
                  ]}
                />
              )}
              {right}
            </div>
          </div>
          <nav className="-mx-1 flex gap-2 overflow-x-auto pb-0.5 lg:hidden">
            {navItems.map((item) => {
              const href = resolveDipeenNavHref(item, roomId);
              const active = isRouteActive({ activeLabels, href, label: item.label, pathname });
              return (
                <Link
                  className={cn(
                    "inline-flex min-h-9 shrink-0 items-center gap-2 rounded-lg border px-3 text-xs font-bold",
                    active
                      ? "border-[var(--ds-primary)] bg-[var(--ds-primary-soft)] text-[var(--ds-primary)]"
                      : "border-[var(--ds-border)] bg-[var(--ds-surface)] text-[var(--ds-text-muted)]",
                  )}
                  href={href}
                  key={item.label}
                >
                  <BrandIcon name={item.icon} size={14} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>
        {children}
      </main>
    </div>
  );
}
