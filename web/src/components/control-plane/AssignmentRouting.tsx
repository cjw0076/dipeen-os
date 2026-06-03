"use client";

import { useEffect, useState } from "react";
import { api, type AssignmentSpec, type RoutingPreview } from "@/lib/api";

// User는 사람·역할·repo만 고른다. role./repo./workspace://는 백엔드가 capability로 번역(숨은 배관).
const ROLES = ["frontend", "backend", "qa", "integrator"];

/**
 * Assign + Routing Preview — 회의에서 정한 작업을 "누구에게" 보낼지 고르고, 즉시 target worker를 본다.
 * 배정 → CommandProposal(assignment) → confirm 시 맞는 worker만 lease. (web UI 갭 #3 Gate3)
 */
export function AssignmentRouting({ roomId }: { roomId: string }) {
  const [intent, setIntent] = useState("");
  const [role, setRole] = useState("");
  const [repo, setRepo] = useState("");
  const [provider, setProvider] = useState("claude");
  const [preview, setPreview] = useState<RoutingPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const hasAssignment = Boolean(role || repo);
  const assignment: AssignmentSpec = {
    role: role || null,
    repo: repo || null,
    workspace_ref: repo ? `workspace://${repo}` : null,
    provider,
  };

  // 배정이 바뀔 때마다 "이 작업은 누구에게?" 미리보기 (디바운스)
  useEffect(() => {
    if (!hasAssignment) { setPreview(null); return; }
    let cancelled = false;
    const t = setTimeout(() => {
      api.routing.preview(assignment, provider)
        .then((p) => { if (!cancelled) setPreview(p); })
        .catch(() => { if (!cancelled) setPreview(null); });
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, repo, provider]);

  const propose = async () => {
    if (!intent.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      const p = await api.proposals.create({
        room_id: roomId,
        intent: intent.trim(),
        provider,
        assignment: hasAssignment ? assignment : undefined,
      });
      setResult(`✓ 제안 ${p.proposal_id.slice(0, 12)} 생성 — Confirm하면 ${preview?.deliverable ? "배정된 worker가" : "(받을 worker 없음)"} 실행`);
      setIntent("");
    } catch (e) {
      setResult(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_10px_34px_rgba(15,23,42,0.06)]">
      <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
        <h2 className="text-[13px] font-semibold text-slate-950">Assign Work → Who gets it</h2>
        <span className="text-[11px] text-slate-400">사람·역할로 배정 · 라우팅 미리보기</span>
      </div>

      <div className="space-y-3 p-4">
        <textarea
          className="min-h-[64px] w-full resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 outline-none ring-blue-200 placeholder:text-slate-400 focus:ring-2"
          onChange={(e) => setIntent(e.target.value)}
          placeholder="예: 온보딩 초대 플로우를 구현하고 검증된 code_patch를 만들어주세요"
          value={intent}
        />
        <div className="grid grid-cols-[1fr_1fr_120px] gap-2">
          <select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none ring-blue-200 focus:ring-2"
            onChange={(e) => setRole(e.target.value)} value={role}>
            <option value="">역할 선택…</option>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <input className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none ring-blue-200 placeholder:text-slate-400 focus:ring-2"
            onChange={(e) => setRepo(e.target.value)} placeholder="repo (예: web-app)" value={repo} />
          <select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none ring-blue-200 focus:ring-2"
            onChange={(e) => setProvider(e.target.value)} value={provider}>
            <option value="claude">Claude</option>
            <option value="codex">Codex</option>
          </select>
        </div>

        {/* Routing Preview — "→ 누구에게" */}
        {hasAssignment && (
          <div className={`rounded-lg border px-3 py-2 text-[12px] ${
            !preview ? "border-slate-200 bg-slate-50 text-slate-500"
              : preview.deliverable ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-amber-200 bg-amber-50 text-amber-800"}`}>
            {!preview ? "라우팅 확인 중…" : preview.deliverable ? (
              <>→ {preview.matching_workers.filter((w) => w.online).map((w) => (
                <span key={w.worker_id} className="font-semibold">{w.user || w.worker_id}{w.workspace_available ? " ✓" : " (workspace 없음)"} </span>
              ))}<span className="text-emerald-600">· {preview.reason}</span></>
            ) : (
              <>받을 worker 없음 — <span className="text-amber-700">{preview.reason}</span></>
            )}
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-slate-500">제안만으론 실행 안 됨 — Confirm이 유일한 실행 경계.</p>
          <button className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={!intent.trim() || busy} onClick={propose} type="button">
            {busy ? "제안 중…" : "Propose"}
          </button>
        </div>
        {result && <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] text-slate-700">{result}</p>}
      </div>
    </section>
  );
}
