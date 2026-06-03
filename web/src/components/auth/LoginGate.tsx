"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/auth";
import { getApiBaseUrl, isLocalApiBase } from "@/lib/api-base";

export function LoginGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    async function bootstrap() {
      // 이미 토큰 있으면 바로 통과
      if (auth.isAuthenticated()) {
        setReady(true);
        return;
      }

      // 로컬 개발(API가 localhost): UI를 직접 띄워 확인할 수 있게 통과시킨다.
      // dev-token bootstrap은 backend에 DIPEEN_DEV_TOKEN이 설정된 경우에만 켠다.
      const apiBase = getApiBaseUrl();
      const isLocal = isLocalApiBase(apiBase);
      if (isLocal) {
        const shouldTryDevToken =
          process.env.NEXT_PUBLIC_ENABLE_DEV_TOKEN === "true" || !process.env.NEXT_PUBLIC_API_URL;
        if (shouldTryDevToken) {
          const controller = new AbortController();
          const timeout = window.setTimeout(() => controller.abort(), 800);
          try {
            const res = await fetch(`${apiBase}/api/auth/dev-token`, {
              signal: controller.signal,
            });
            if (res.ok) {
              const data = await res.json();
              auth.setToken(data.access_token);
              setReady(true);
              return;
            }
          } catch {
            // UI-only local preview: backend can be down while design work continues.
          } finally {
            window.clearTimeout(timeout);
          }
        }
        auth.setToken("dev-ui-demo-token");
        setReady(true);
        return;
      }

      router.replace("/login");
    }

    bootstrap();
  }, [router]);

  if (!ready) return null;
  return <>{children}</>;
}
