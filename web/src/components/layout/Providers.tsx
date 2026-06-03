"use client";

import { useEffect } from "react";
import { wsManager } from "@/lib/ws";
import { LoginGate } from "@/components/auth/LoginGate";
import { getApiBaseUrl, deriveWsUrl } from "@/lib/api-base";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const wsUrl = deriveWsUrl(getApiBaseUrl(), "/ws/events");
    wsManager.connect(wsUrl);
    return () => wsManager.disconnect();
  }, []);

  return <LoginGate>{children}</LoginGate>;
}
