"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";

type UsageSummary = {
  period_days: number;
  total_tokens: number;
  today_tokens: number;
  by_agent: Record<string, number>;
  by_agent_model: Record<string, string>;
  estimated_cost_usd: number;
  snapshot_at: string;
};

const PERIODS = [
  { label: "7d",  days: 7  },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
];

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function UsageDashboard() {
  const [period, setPeriod] = useState(30);
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.usage.summary(period)
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [period]);

  const agentEntries = data
    ? Object.entries(data.by_agent).sort((a, b) => b[1] - a[1])
    : [];
  const maxTokens = agentEntries.length > 0 ? agentEntries[0][1] : 1;

  return (
    <div className="space-y-5">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-text-muted">Period:</span>
        <div className="flex gap-1">
          {PERIODS.map(p => (
            <button
              key={p.days}
              onClick={() => setPeriod(p.days)}
              className={`px-2.5 py-1 text-[11px] rounded-md border transition-colors ${
                period === p.days
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border text-text-muted hover:text-text-secondary"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="py-8 text-center text-[12px] text-text-muted">Loading...</div>
      )}

      {error && (
        <div className="py-4 text-[12px] text-red-400">Error: {error}</div>
      )}

      {!loading && data && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-border bg-bg-elevated/40 p-3 space-y-1">
              <p className="text-[10px] text-text-muted uppercase tracking-widest">Total Tokens</p>
              <p className="text-[20px] font-semibold tabular-nums">{fmt(data.total_tokens)}</p>
              <p className="text-[10px] text-text-muted">{period}d window</p>
            </div>
            <div className="rounded-xl border border-border bg-bg-elevated/40 p-3 space-y-1">
              <p className="text-[10px] text-text-muted uppercase tracking-widest">Today</p>
              <p className="text-[20px] font-semibold tabular-nums">{fmt(data.today_tokens)}</p>
              <p className="text-[10px] text-text-muted">tokens used</p>
            </div>
            <div className="rounded-xl border border-border bg-bg-elevated/40 p-3 space-y-1">
              <p className="text-[10px] text-text-muted uppercase tracking-widest">Est. Cost</p>
              <p className="text-[20px] font-semibold tabular-nums">
                ${data.estimated_cost_usd.toFixed(3)}
              </p>
              <p className="text-[10px] text-text-muted">USD ({period}d)</p>
            </div>
          </div>

          {/* By agent bar chart */}
          {agentEntries.length > 0 && (
            <div className="space-y-2">
              <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest">
                By Agent
              </p>
              <div className="space-y-2">
                {agentEntries.map(([agentId, tokens]) => {
                  const model = data.by_agent_model[agentId] ?? "—";
                  const pct = Math.round((tokens / maxTokens) * 100);
                  return (
                    <div key={agentId} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-[12px] font-mono text-text-primary truncate">
                            {agentId}
                          </span>
                          <span className="text-[10px] text-text-muted shrink-0">
                            {model}
                          </span>
                        </div>
                        <span className="text-[11px] tabular-nums text-text-secondary shrink-0 ml-2">
                          {fmt(tokens)}
                        </span>
                      </div>
                      <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                        <div
                          className="h-full bg-accent/70 rounded-full transition-all duration-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {agentEntries.length === 0 && (
            <p className="text-[12px] text-text-muted py-4">
              아직 사용 데이터 없음 ({period}일 기준).
            </p>
          )}
        </>
      )}
    </div>
  );
}
