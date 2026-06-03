"use client";

import { useEffect } from "react";
import { wsManager } from "@/lib/ws";
import { LoginGate } from "@/components/auth/LoginGate";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const apiOverride = localStorage.getItem("dipeen_api_url");
    const wsUrl = apiOverride?.trim()
      ? apiOverride.trim().replace(/^http/, "ws") + "/ws/events"
      : (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/events");
    wsManager.connect(wsUrl);
    return () => wsManager.disconnect();
  }, []);

  return <LoginGate>{children}</LoginGate>;
}
