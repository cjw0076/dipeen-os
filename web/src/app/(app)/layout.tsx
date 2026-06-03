"use client";

import { Providers } from "@/components/layout/Providers";
import { AgentPanelProvider } from "@/contexts/AgentPanelContext";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <AgentPanelProvider>{children}</AgentPanelProvider>
    </Providers>
  );
}
