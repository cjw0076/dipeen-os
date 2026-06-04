"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { BrandIcon } from "@/components/ui/brand-icons";
import {
  PROMPT_PRESETS,
  expandSlashCommand,
  matchingSlashCommands,
  type SlashCommand,
} from "@/lib/command-presets";

function cn(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type CommandComposerProps = {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: (expandedText: string) => void;
  readonly busy?: boolean;
  readonly minRows?: number;
  readonly placeholder?: string;
  readonly submitLabel?: string;
  readonly tone?: "light" | "dark";
};

export function CommandComposer({
  value,
  onChange,
  onSubmit,
  busy = false,
  minRows = 2,
  placeholder = "Type / for commands",
  submitLabel = "Send",
  tone = "light",
}: CommandComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [selected, setSelected] = useState(0);
  const suggestions = useMemo(() => matchingSlashCommands(value), [value]);
  const isDark = tone === "dark";

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    setSelected(0);
  }, [value]);

  const applyCommand = (command: SlashCommand) => {
    const rest = value.trimStart().replace(/^\/\S*/, "").trim();
    onChange(`${command.name}${rest ? ` ${rest}` : command.placeholder ? ` ${command.placeholder}` : ""}`);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const submit = () => {
    const expanded = expandSlashCommand(value);
    if (!expanded.trim()) return;
    onSubmit(expanded);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (suggestions.length && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      setSelected((current) => {
        const delta = event.key === "ArrowDown" ? 1 : -1;
        return (current + delta + suggestions.length) % suggestions.length;
      });
      return;
    }
    if (suggestions.length && (event.key === "Tab" || event.key === "Enter") && value.trimStart().match(/^\/\S*$/)) {
      event.preventDefault();
      applyCommand(suggestions[selected] ?? suggestions[0]);
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className={cn("relative rounded-lg border p-2 shadow-sm", isDark ? "border-border bg-bg-elevated" : "border-slate-200 bg-white")}>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {PROMPT_PRESETS.map((preset) => (
          <button
            className={cn(
              "rounded-md border px-2 py-1 text-[11px] font-semibold transition-colors",
              isDark
                ? "border-border-subtle bg-bg-card text-text-secondary hover:border-accent/50"
                : "border-slate-200 bg-slate-50 text-slate-600 hover:border-blue-300 hover:bg-blue-50",
            )}
            key={preset.label}
            onClick={() => {
              onChange(preset.value);
              requestAnimationFrame(() => inputRef.current?.focus());
            }}
            type="button"
          >
            {preset.label}
          </button>
        ))}
        <span className={cn("ml-auto rounded-md px-2 py-1 font-mono text-[10px]", isDark ? "text-text-muted" : "text-slate-400")}>Ctrl K</span>
      </div>

      {suggestions.length > 0 && (
        <div className={cn("absolute bottom-full left-2 right-2 z-20 mb-2 overflow-hidden rounded-lg border shadow-xl", isDark ? "border-border bg-bg-card" : "border-slate-200 bg-white")}>
          {suggestions.map((command, index) => (
            <button
              className={cn(
                "grid w-full grid-cols-[auto_1fr] gap-2 px-3 py-2 text-left",
                index === selected ? (isDark ? "bg-accent/15" : "bg-blue-50") : "",
              )}
              key={command.name}
              onClick={() => applyCommand(command)}
              type="button"
            >
              <BrandIcon className={isDark ? "mt-0.5 text-accent-hover" : "mt-0.5 text-blue-600"} name="command" size={15} />
              <span className="min-w-0">
                <span className={cn("block text-[12px] font-bold", isDark ? "text-text-primary" : "text-slate-900")}>{command.name} · {command.title}</span>
                <span className={cn("block truncate text-[11px]", isDark ? "text-text-muted" : "text-slate-500")}>{command.description}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
        <textarea
          className={cn(
            "w-full resize-none rounded-md border px-3 py-2 text-sm leading-6 outline-none",
            isDark
              ? "border-border-subtle bg-bg-primary text-text-primary placeholder:text-text-muted focus:border-accent/60"
              : "border-[var(--ds-border)] bg-[var(--ds-surface-raised)] text-[var(--ds-text)] placeholder:text-[var(--ds-text-subtle)] focus:border-[#c89455]",
          )}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          ref={inputRef}
          rows={minRows}
          value={value}
        />
        <button
          className={cn(
            "h-10 self-start rounded-md px-3 py-2 text-xs font-bold text-white shadow-sm disabled:opacity-50",
            isDark ? "bg-accent hover:bg-accent-hover" : "bg-[#b98545] hover:bg-[#a47438]",
          )}
          disabled={busy || !value.trim()}
          onClick={submit}
          type="button"
        >
          {submitLabel}
        </button>
      </div>
    </div>
  );
}
