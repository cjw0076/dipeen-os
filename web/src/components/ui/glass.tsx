import type { HTMLAttributes, ReactNode } from "react";
import { BrandIcon, type BrandIconName } from "./brand-icons";

type Tone = "blue" | "emerald" | "violet" | "amber" | "neutral" | "danger";
type Padding = "none" | "xs" | "sm" | "md";

const toneClasses: Record<Tone, string> = {
  blue: "border-agent-fe/35 bg-agent-fe/10 text-agent-fe shadow-[0_0_24px_rgba(96,165,250,0.14)]",
  emerald: "border-agent-be/35 bg-agent-be/10 text-agent-be shadow-[0_0_24px_rgba(52,211,153,0.14)]",
  violet: "border-agent-qa/35 bg-agent-qa/10 text-agent-qa shadow-[0_0_24px_rgba(167,139,250,0.14)]",
  amber: "border-agent-pm/35 bg-agent-pm/10 text-agent-pm shadow-[0_0_24px_rgba(251,191,36,0.12)]",
  neutral: "border-white/10 bg-white/[0.04] text-text-secondary shadow-[0_0_22px_rgba(255,255,255,0.06)]",
  danger: "border-status-error/35 bg-status-error/10 text-status-error shadow-[0_0_24px_rgba(239,68,68,0.12)]",
};

const paddingClasses: Record<Padding, string> = {
  none: "",
  xs: "p-2",
  sm: "p-3",
  md: "p-4",
};

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function GlassPanel({
  className,
  padding = "sm",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { padding?: Padding }) {
  return (
    <div
      className={cx(
        "rounded-lg border border-white/[0.08] bg-white/[0.045] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_18px_40px_rgba(0,0,0,0.18)] backdrop-blur-xl",
        paddingClasses[padding],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function GlassChip({
  className,
  tone = "neutral",
  children,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] font-medium leading-none",
        toneClasses[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

export function IconBadge({
  icon,
  tone = "neutral",
  size = "md",
  className,
  children,
}: {
  icon: BrandIconName;
  tone?: Tone;
  size?: "sm" | "md" | "lg";
  className?: string;
  children?: ReactNode;
}) {
  const sizeClass = size === "lg" ? "h-11 w-11" : size === "sm" ? "h-7 w-7" : "h-9 w-9";
  const iconSize = size === "lg" ? 23 : size === "sm" ? 15 : 18;

  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-lg border",
        sizeClass,
        toneClasses[tone],
        className,
      )}
    >
      {children ?? <BrandIcon name={icon} size={iconSize} />}
    </span>
  );
}
