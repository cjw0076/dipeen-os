"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/auth";
import { api } from "@/lib/api";
import { dipeenSpatialAssets } from "@/design-system/dipeen-spatial";
import { SpatialButton, SpatialIdentityMark, SpatialNotice, SpatialPanel, SpatialSegmentedControl } from "@/components/spatial";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [launcherNotice, setLauncherNotice] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (mode === "signup") {
        const res = await api.auth.signup(email, password, name);
        auth.setToken(res.access_token);
        localStorage.setItem("dipeen_user_name", res.name);
        // 팀이 아직 없으면 제거된 onboarding route 대신 brand office로 보낸다.
        if (!res.team_id || res.team_id === "default-team") {
          router.push("/office");
        } else {
          router.push("/");
        }
      } else {
        const res = await api.auth.login(email, password);
        auth.setToken(res.access_token);
        localStorage.setItem("dipeen_user_name", res.name);
        if (!res.team_id || res.team_id === "default-team") {
          router.push("/office");
        } else {
          router.push("/");
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "An error occurred";
      if (msg.includes("409")) setError("This email is already registered.");
      else if (msg.includes("401")) setError("Invalid email or password.");
      else if (msg.includes("422")) setError(msg.replace(/^API \d+: /, ""));
      else setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid h-screen w-screen bg-[#fbf4e8] text-slate-950 lg:grid-cols-[minmax(0,1.35fr)_minmax(440px,0.65fr)]">
      <section className="relative hidden overflow-hidden lg:block">
        <img
          alt="Warm isometric Dipeen office"
          className="absolute inset-0 h-full w-full object-cover"
          draggable={false}
          src={dipeenSpatialAssets.backgrounds.light}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#fbf4e8]/80 via-[#fbf4e8]/28 to-transparent" />
        <div className="relative z-10 flex h-full flex-col justify-between p-14">
          <div>
            <SpatialIdentityMark size="lg" />
            <h1 className="mt-12 max-w-xl text-3xl font-bold leading-tight text-[#13233a]">Sign in to your workspace</h1>
            <p className="mt-4 max-w-md text-base leading-7 text-slate-600">
              Dipeen is the source of truth for your team&apos;s work, runs, artifacts, permissions, and memory.
            </p>
          </div>
          <SpatialNotice className="max-w-sm bg-white/88 backdrop-blur-md" icon="shield" title="Your keys. Your control." tone="primary">
            Credentials stay on the worker machine. Dipeen receives signed requests and reconciled state.
          </SpatialNotice>
        </div>
      </section>

      <main className="flex min-h-0 items-center justify-center overflow-auto border-l border-[#e4d7c2] bg-white/72 p-6 backdrop-blur-sm">
        <div className="w-full max-w-[520px]">
          <div className="mb-6 flex justify-end gap-3">
            <SpatialSegmentedControl items={[{ label: "Light", active: true }, { label: "Dark" }]} />
            <SpatialSegmentedControl items={[{ label: "EN", active: true }, { label: "KO" }]} />
          </div>

          <SpatialPanel className="p-8">
            <div className="flex items-center gap-3 lg:hidden">
              <SpatialIdentityMark />
            </div>

            <div className="mt-0 lg:mt-0">
              <label className="block text-sm font-bold text-[#13233a]">Workspace URL</label>
              <div className="mt-3 flex items-center gap-3 rounded-lg border border-[#e4d7c2] bg-[#fffdf8] px-4 py-3">
                <img alt="" className="size-5 opacity-75" src={dipeenSpatialAssets.icons.office} />
                <span className="flex-1 text-sm font-semibold text-slate-700">app.dipeen.ai</span>
                <span className="rounded-full bg-[#e7f5ee] px-2 py-1 text-[11px] font-bold text-[#4c9a74]">Saved</span>
              </div>
            </div>

            <div className="mt-8">
              <h2 className="text-lg font-bold text-[#13233a]">
                {mode === "login" ? "Sign in with your identity" : "Create your account"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {mode === "login"
                  ? "Use your Dipeen account. Passkey and launcher identity can be connected during onboarding."
                  : "Create an account, then configure launcher identity and BYOK during onboarding."}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              {mode === "signup" && (
                <div>
                  <label className="block text-[12px] font-semibold text-slate-600">Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your name"
                    className="mt-2 w-full rounded-lg border border-[#e4d7c2] bg-[#fffdf8] px-4 py-3 text-sm text-slate-950 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/10"
                    required
                    autoFocus
                  />
                </div>
              )}

              <div>
                <label className="block text-[12px] font-semibold text-slate-600">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="mt-2 w-full rounded-lg border border-[#e4d7c2] bg-[#fffdf8] px-4 py-3 text-sm text-slate-950 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/10"
                  required
                  autoFocus={mode === "login"}
                />
              </div>

              <div>
                <label className="block text-[12px] font-semibold text-slate-600">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "signup" ? "At least 8 characters" : "Your password"}
                  className="mt-2 w-full rounded-lg border border-[#e4d7c2] bg-[#fffdf8] px-4 py-3 text-sm text-slate-950 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-500/10"
                  required
                  minLength={mode === "signup" ? 8 : undefined}
                />
              </div>

              {error && (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700">
                  {error}
                </p>
              )}

              <SpatialButton
                type="submit"
                disabled={loading}
                className="w-full"
              >
                {loading ? "..." : mode === "login" ? "Sign In" : "Create Account"}
              </SpatialButton>
            </form>

            <div className="my-6 flex items-center gap-4 text-xs text-slate-400">
              <span className="h-px flex-1 bg-[#e4d7c2]" />
              <span>or</span>
              <span className="h-px flex-1 bg-[#e4d7c2]" />
            </div>

            <SpatialButton
              className="w-full justify-between"
              icon="play"
              onClick={() => {
                setLauncherNotice("Launcher identity is configured from the Dipeen Office surface.");
                router.push("/office");
              }}
              variant="secondary"
              type="button"
            >
              <span>Open Dipeen Office</span>
              <span className="rounded-full bg-[#e7f5ee] px-2 py-1 text-[11px] text-[#4c9a74]">Ready</span>
            </SpatialButton>
            {launcherNotice && <p className="mt-3 text-xs text-slate-500">{launcherNotice}</p>}

            <SpatialNotice className="mt-6" icon="key" title="Bring Your Own Key (BYOK)" tone="honey">
              Dipeen never stores provider keys. Agent workers sign actions locally and report canonical state back to Dipeen.
            </SpatialNotice>

            <div className="mt-6 text-center">
              <button
                onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}
                className="text-[12px] font-semibold text-slate-500 transition hover:text-blue-700"
              >
                {mode === "login"
                  ? "Don't have an account? Sign up"
                  : "Already have an account? Sign in"}
              </button>
            </div>
          </SpatialPanel>
          <p className="mt-5 text-center text-xs text-slate-500">Security boundary: cryptographic operations are performed locally.</p>
        </div>
      </main>
    </div>
  );
}
