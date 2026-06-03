import type { BrandIconName } from "@/components/ui/brand-icons";

export type DipeenNavItem = {
  href: string;
  icon: BrandIconName;
  label: string;
};

export const dipeenNavItems: DipeenNavItem[] = [
  { href: "/app", icon: "command", label: "Overview" },
  { href: "/flow", icon: "workflow", label: "Flow" },
  { href: "/meeting/general", icon: "spark", label: "Goals" },
  { href: "/app", icon: "board", label: "Tasks" },
  { href: "/dashboard", icon: "play", label: "Runs" },
  { href: "/dashboard", icon: "database", label: "Artifacts" },
  { href: "/meeting/general", icon: "chat", label: "Discussions" },
  { href: "/app", icon: "shield", label: "Permissions" },
  { href: "/app", icon: "layers", label: "Memory" },
  { href: "/settings", icon: "workflow", label: "Providers" },
  { href: "/settings", icon: "settings", label: "Settings" },
  { href: "/onboarding", icon: "key", label: "BYOK Onboarding" },
];

export function resolveDipeenNavHref(item: DipeenNavItem, roomId?: string) {
  if (item.href.startsWith("/meeting/")) return `/meeting/${roomId || "general"}`;
  return item.href;
}
