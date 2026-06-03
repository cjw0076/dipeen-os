"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface AgentPanelState {
  selectedAgentId: string | null;
  selectedAgentLabel: string | null;
  openAgentPanel: (agentId: string, label: string) => void;
  closeAgentPanel: () => void;
}

const AgentPanelCtx = createContext<AgentPanelState>({
  selectedAgentId: null,
  selectedAgentLabel: null,
  openAgentPanel: () => {},
  closeAgentPanel: () => {},
});

export function AgentPanelProvider({ children }: { children: ReactNode }) {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedAgentLabel, setSelectedAgentLabel] = useState<string | null>(null);

  const openAgentPanel = useCallback((agentId: string, label: string) => {
    setSelectedAgentId(agentId);
    setSelectedAgentLabel(label);
  }, []);

  const closeAgentPanel = useCallback(() => {
    setSelectedAgentId(null);
    setSelectedAgentLabel(null);
  }, []);

  return (
    <AgentPanelCtx.Provider value={{ selectedAgentId, selectedAgentLabel, openAgentPanel, closeAgentPanel }}>
      {children}
    </AgentPanelCtx.Provider>
  );
}

export function useAgentPanel() {
  return useContext(AgentPanelCtx);
}
