"use client";

// ux-command-layer-v0 — ⌘K palette. Enumerates runnable slash templates from
// /api/control/capabilities (curated verbs + capability catalog). Selecting a command either
// runs it immediately (needs_input=false) or hands the template to the prompt box to finish
// (needs_input=true). Keyboard: ↑/↓ to move, Enter to choose, Esc to close.

import { useEffect, useMemo, useRef, useState } from "react";
import { api, type PaletteCommand } from "@/lib/api";

export function CommandPalette({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (cmd: PaletteCommand) => void;
}) {
  const [commands, setCommands] = useState<PaletteCommand[]>([]);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    api.control
      .capabilities()
      .then((r) => setCommands(r.commands))
      .catch(() => setCommands([]));
    const focus = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(focus);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.template.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q),
    );
  }, [commands, query]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  if (!open) return null;

  const clampedActive = Math.min(active, Math.max(0, filtered.length - 1));

  const handleKey = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, filtered.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const cmd = filtered[clampedActive];
      if (cmd) onSelect(cmd);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/30 p-4 pt-[12vh]"
      onMouseDown={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-[var(--ds-border)] bg-[var(--ds-surface)] shadow-[var(--ds-shadow-floating)]"
        onKeyDown={handleKey}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Command palette"
      >
        <input
          ref={inputRef}
          className="w-full border-b border-[var(--ds-border)] bg-transparent px-4 py-3 text-sm text-[var(--ds-text)] outline-none placeholder:text-[var(--ds-text-muted)]"
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Run a Dipeen command — assign, approve, status, expose…"
          value={query}
        />
        <ul className="max-h-[50vh] overflow-y-auto py-1">
          {filtered.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-[var(--ds-text-muted)]">No matching command.</li>
          )}
          {filtered.map((cmd, i) => (
            <li key={cmd.id}>
              <button
                className={
                  "flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm " +
                  (i === clampedActive ? "bg-[var(--ds-surface-warm)]" : "")
                }
                onClick={() => onSelect(cmd)}
                onMouseEnter={() => setActive(i)}
                type="button"
              >
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-[var(--ds-text)]">{cmd.label}</span>
                  <span className="block truncate text-[11px] text-[var(--ds-text-muted)]">{cmd.template.trim()}</span>
                </span>
                {cmd.needs_input && (
                  <span className="shrink-0 rounded-md border border-[var(--ds-border)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--ds-text-muted)]">
                    needs input
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
        <div className="flex items-center justify-between border-t border-[var(--ds-border)] px-4 py-2 text-[11px] text-[var(--ds-text-muted)]">
          <span>↑ ↓ to move · Enter to run · Esc to close</span>
          <span>⌘K</span>
        </div>
      </div>
    </div>
  );
}
