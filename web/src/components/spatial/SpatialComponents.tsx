"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { BrandIcon, type BrandIconName } from "@/components/ui/brand-icons";

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export type SpatialTone = "primary" | "sage" | "honey" | "coral" | "violet" | "slate";

const badgeToneClass: Record<SpatialTone, string> = {
  primary: "bg-[#e9edff] text-[#3e63dd] ring-[#cbd5ff]",
  sage: "bg-[#e7f5ee] text-[#4c9a74] ring-[#bfe6d1]",
  honey: "bg-[#fff2cc] text-[#d99a18] ring-[#f5d98a]",
  coral: "bg-[#ffe7e2] text-[#d85e4f] ring-[#f2bbb2]",
  violet: "bg-[#efeaff] text-[#7b5ce1] ring-[#d7cbff]",
  slate: "bg-slate-100 text-slate-600 ring-slate-200",
};

type SpatialIdentityMarkProps = {
  compact?: boolean;
  className?: string;
  labelClassName?: string;
  size?: "sm" | "md" | "lg";
};

export function SpatialIdentityMark({ compact = false, className, labelClassName, size = "md" }: SpatialIdentityMarkProps) {
  const markSize = {
    sm: "size-9 rounded-[8px] text-base",
    md: "size-10 rounded-[8px] text-lg",
    lg: "size-16 rounded-[8px] text-3xl",
  }[size];
  const labelSize = {
    sm: "text-xl",
    md: "text-2xl",
    lg: "text-5xl",
  }[size];
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <span className={cn("grid shrink-0 place-items-center bg-gradient-to-br from-[#caa06a] to-[#8f6230] font-black text-white shadow-[0_14px_32px_rgba(143,98,48,0.24)]", markSize)}>
        D
      </span>
      {!compact && <span className={cn("font-bold tracking-tight text-[#13233a]", labelSize, labelClassName)}>Dipeen</span>}
    </div>
  );
}

type SpatialPanelProps = {
  children: ReactNode;
  className?: string;
  title?: string;
  description?: string;
  icon?: BrandIconName;
  action?: ReactNode;
};

export function SpatialPanel({ children, className, title, description, icon, action }: SpatialPanelProps) {
  return (
    <section className={cn("ds-panel overflow-hidden", className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-[var(--ds-border)] px-5 py-4">
          <div className="min-w-0">
            {title && (
              <div className="flex items-center gap-2">
                {icon && <BrandIcon className="shrink-0 text-[var(--ds-primary)]" name={icon} size={18} />}
                <h2 className="text-sm font-bold leading-5 text-[var(--ds-text)]">{title}</h2>
              </div>
            )}
            {description && <p className="mt-1 text-xs leading-5 text-[var(--ds-text-muted)]">{description}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function SpatialCard({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("ds-card", className)}>{children}</div>;
}

type SpatialBadgeProps = {
  children: ReactNode;
  tone?: SpatialTone;
  className?: string;
};

export function SpatialBadge({ children, tone = "slate", className }: SpatialBadgeProps) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-bold ring-1", badgeToneClass[tone], className)}>
      {children}
    </span>
  );
}

type SpatialButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  icon?: BrandIconName;
};

export function SpatialButton({ children, className, variant = "primary", icon, type = "button", ...props }: SpatialButtonProps) {
  const variantClass = {
    primary: "border-transparent bg-[var(--ds-primary)] text-white shadow-[0_12px_28px_rgba(62,99,221,0.28)] hover:bg-blue-700",
    secondary: "border-[var(--ds-border)] bg-[var(--ds-surface-raised)] text-[var(--ds-text)] hover:border-[var(--ds-border-strong)]",
    ghost: "border-transparent bg-transparent text-[var(--ds-text-muted)] hover:bg-[var(--ds-primary-soft)] hover:text-[var(--ds-primary)]",
    danger: "border-red-200 bg-red-50 text-red-700 hover:bg-red-100",
  }[variant];
  return (
    <button
      className={cn("inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-50", variantClass, className)}
      type={type}
      {...props}
    >
      {icon && <BrandIcon name={icon} size={16} />}
      {children}
    </button>
  );
}

type SpatialSegmentedControlProps = {
  items: Array<{ label: string; active?: boolean; icon?: BrandIconName; onClick?: () => void }>;
  className?: string;
};

export function SpatialSegmentedControl({ items, className }: SpatialSegmentedControlProps) {
  return (
    <div className={cn("inline-flex rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-raised)] p-1 text-xs font-bold text-[var(--ds-text-muted)] shadow-[0_10px_24px_rgba(68,56,38,0.08)]", className)}>
      {items.map((item) => (
        <button
          className={cn(
            "inline-flex min-h-8 items-center gap-1.5 rounded-md px-3 transition",
            item.active ? "bg-[var(--ds-primary-soft)] text-[var(--ds-primary)] shadow-sm" : "hover:bg-[var(--ds-bg-muted)] hover:text-[var(--ds-text)]"
          )}
          key={item.label}
          onClick={item.onClick}
          type="button"
        >
          {item.icon && <BrandIcon name={item.icon} size={14} />}
          {item.label}
        </button>
      ))}
    </div>
  );
}

type SpatialNoticeProps = {
  title: string;
  children: ReactNode;
  icon?: BrandIconName;
  tone?: SpatialTone;
  className?: string;
};

export function SpatialNotice({ title, children, icon = "shield", tone = "honey", className }: SpatialNoticeProps) {
  const iconColor = {
    primary: "text-[var(--ds-primary)]",
    sage: "text-[var(--ds-sage)]",
    honey: "text-[var(--ds-honey)]",
    coral: "text-[var(--ds-coral)]",
    violet: "text-[var(--ds-violet)]",
    slate: "text-[var(--ds-text-muted)]",
  }[tone];
  return (
    <div className={cn("ds-nudge flex items-start gap-3", className)}>
      <BrandIcon className={cn("mt-0.5 shrink-0", iconColor)} name={icon} size={22} />
      <div className="min-w-0">
        <p className="text-sm font-bold text-[var(--ds-text)]">{title}</p>
        <div className="mt-1 text-sm leading-6 text-[var(--ds-text-muted)]">{children}</div>
      </div>
    </div>
  );
}

type SpatialMetricCardProps = {
  label: string;
  value: string | number;
  caption?: string;
  tone?: SpatialTone;
  icon?: BrandIconName;
};

export function SpatialMetricCard({ label, value, caption, tone = "primary", icon }: SpatialMetricCardProps) {
  const valueTone = {
    primary: "text-[var(--ds-primary)]",
    sage: "text-[var(--ds-sage)]",
    honey: "text-[var(--ds-honey)]",
    coral: "text-[var(--ds-coral)]",
    violet: "text-[var(--ds-violet)]",
    slate: "text-[var(--ds-text)]",
  }[tone];
  return (
    <SpatialCard className="min-h-[112px]">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold text-[var(--ds-text-muted)]">{label}</p>
        {icon && <BrandIcon className="text-[var(--ds-text-subtle)]" name={icon} size={16} />}
      </div>
      <p className={cn("mt-3 text-3xl font-bold", valueTone)}>{value}</p>
      {caption && <p className="mt-1 text-xs text-[var(--ds-text-subtle)]">{caption}</p>}
    </SpatialCard>
  );
}

type SpatialOfficeCanvasFrameProps = {
  children: ReactNode;
  className?: string;
  label?: string;
};

export function SpatialOfficeCanvasFrame({ children, className, label = "Spatial Office Canvas" }: SpatialOfficeCanvasFrameProps) {
  return (
    <section aria-label={label} className={cn("ds-office-surface relative min-w-0 overflow-hidden", className)}>
      {children}
    </section>
  );
}
