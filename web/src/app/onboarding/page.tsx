"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { auth } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/api-base";
import { dipeenSpatialAssets } from "@/design-system/dipeen-spatial";
import { SpatialButton, SpatialIdentityMark, SpatialNotice, SpatialPanel } from "@/components/spatial";

function OnboardingInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [apiBase, setApiBase] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [joined, setJoined] = useState<{ team_id: string } | null>(null);
  const [copied, setCopied] = useState("");

  // Invite link carries ?code= and (for remote tunnels) ?api= → persist API base so this
  // page + later web sessions talk to the right HQ. Keys/credentials never travel here.
  useEffect(() => {
    const apiOverride = params.get("api");
    if (apiOverride?.trim()) localStorage.setItem("dipeen_api_url", apiOverride.trim());
    setApiBase(getApiBaseUrl());
    setCode((params.get("code") || "").trim().toUpperCase());
  }, [params]);

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.teams.join(code.trim());
      auth.setToken(res.token);                       // gives this browser Control Tower access
      localStorage.setItem("dipeen_team_id", res.team_id);
      setJoined({ team_id: res.team_id });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to join";
      if (msg.includes("404")) setError("Invite code not found. Check the link or ask for a new code.");
      else if (msg.includes("410")) setError("This invite code has expired. Ask the host for a new one.");
      else setError(msg.replace(/^API \d+: /, ""));
    } finally {
      setLoading(false);
    }
  }

  const workerCommand = `dipeen-agent join "${apiBase}/api/teams/join?code=${code}" --start-worker`;

  function copy(text: string, key: string) {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(""), 1500);
    });
  }

  return (
    <main className="flex min-h-screen w-screen items-center justify-center bg-[#fbf4e8] p-6 text-slate-950">
      <div className="w-full max-w-[560px]">
        <div className="mb-6 flex justify-center">
          <SpatialIdentityMark size="lg" />
        </div>

        <SpatialPanel className="p-8">
          {!joined ? (
            <>
              <h1 className="text-xl font-bold text-[#13233a]">Join the workspace</h1>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                Redeem your invite to join the team. Your provider keys stay on your own machine —
                Dipeen never receives them.
              </p>

              <form onSubmit={handleJoin} className="mt-6 space-y-4">
                <div>
                  <label className="block text-[12px] font-semibold text-slate-600">Workspace (API)</label>
                  <div className="mt-2 flex items-center gap-3 rounded-lg border border-[#e4d7c2] bg-[#fffdf8] px-4 py-3">
                    <img alt="" className="size-5 opacity-75" src={dipeenSpatialAssets.icons.office} />
                    <span className="flex-1 truncate text-sm font-semibold text-slate-700">{apiBase || "…"}</span>
                  </div>
                </div>

                <div>
                  <label className="block text-[12px] font-semibold text-slate-600">Invite code</label>
                  <input
                    type="text"
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase())}
                    placeholder="ABCD1234"
                    className="mt-2 w-full rounded-lg border border-[#e4d7c2] bg-[#fffdf8] px-4 py-3 font-mono text-sm tracking-widest text-slate-950 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/10"
                    required
                    autoFocus
                  />
                </div>

                {error && (
                  <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700">{error}</p>
                )}

                <SpatialButton type="submit" disabled={loading || !code.trim()} className="w-full">
                  {loading ? "Joining…" : "Join workspace"}
                </SpatialButton>
              </form>

              <SpatialNotice className="mt-6" icon="key" title="Bring Your Own Key (BYOK)" tone="honey">
                After joining, attach a local worker. Your Claude / Codex credentials stay on your machine.
              </SpatialNotice>
            </>
          ) : (
            <>
              <h1 className="text-xl font-bold text-[#13233a]">You&apos;re in 🎉</h1>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                Joined team <span className="font-mono font-semibold text-slate-700">{joined.team_id}</span>.
                Now attach a local worker so the team can route work to your machine.
              </p>

              <div className="mt-5">
                <label className="block text-[12px] font-semibold text-slate-600">Run on your machine</label>
                <div className="mt-2 flex items-start gap-2 rounded-lg border border-[#e4d7c2] bg-[#13233a] px-4 py-3">
                  <code className="flex-1 break-all font-mono text-[12px] leading-5 text-[#e7f5ee]">{workerCommand}</code>
                  <button
                    type="button"
                    onClick={() => copy(workerCommand, "cmd")}
                    className="shrink-0 rounded-md bg-white/10 px-2 py-1 text-[11px] font-bold text-white transition hover:bg-white/20"
                  >
                    {copied === "cmd" ? "Copied" : "Copy"}
                  </button>
                </div>
                <p className="mt-2 text-[12px] text-slate-500">
                  No CLI yet? Install first:{" "}
                  <code className="font-mono text-slate-600">pip install -e agent-client</code> — then run the command above.
                </p>
              </div>

              <SpatialButton className="mt-6 w-full" onClick={() => router.push("/")}>
                Open Control Tower
              </SpatialButton>

              <SpatialNotice className="mt-6" icon="shield" title="Permissioned by default" tone="primary">
                Risky actions (push, PR, deploy) become permission requests and run in dry-run until approved.
              </SpatialNotice>
            </>
          )}
        </SpatialPanel>

        <p className="mt-5 text-center text-xs text-slate-500">
          Already have an account? <a href="/login" className="font-semibold text-blue-700">Sign in</a>
        </p>
      </div>
    </main>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<main className="flex min-h-screen items-center justify-center bg-[#fbf4e8] text-slate-500">Loading…</main>}>
      <OnboardingInner />
    </Suspense>
  );
}
