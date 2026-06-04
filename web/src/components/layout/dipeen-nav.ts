import type { BrandIconName } from "@/components/ui/brand-icons";

export type DipeenNavItem = {
  href: string;
  icon: BrandIconName;
  label: string;
};

export const dipeenNavItems: DipeenNavItem[] = [
  { href: "/app", icon: "command", label: "Overview" },
  { href: "/office", icon: "spark", label: "Office" },
];

export function resolveDipeenNavHref(item: DipeenNavItem, _roomId?: string) {
  return item.href;
}
