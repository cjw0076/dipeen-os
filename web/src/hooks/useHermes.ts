"use client";

import { useState, useEffect } from "react";
import { hermesManager, getHermesUrl } from "@/lib/hermes";
import { type WSEvent } from "@/lib/ws";

export type HermesPresence = {
  agent_id: string;
  status: "online" | "offline";
  capabilities?: any;
};

export type HermesLog = {
  task_id: string;
  agent_id: string;
  level: string;
  text: string;
  changed_files: string[];
  tests: any;
  ts: string;
};

export function useHermes(teamId: string = "default-team") {
  const [presence, setPresence] = useState<Record<string, HermesPresence>>({});
  const [logs, setLogs] = useState<HermesLog[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!hermesManager.connected) {
      hermesManager.connect(getHermesUrl(teamId));
    }

    const handler = (e: WSEvent) => {
      const ev = e as any;
      if (ev.type === "PRESENCE_UPDATE") {
        const { agent_id, payload } = ev;
        setPresence((prev) => ({
          ...prev,
          [agent_id]: {
            agent_id,
            status: payload.status,
            capabilities: payload.capabilities,
          },
        }));
      } else if (ev.type === "LOG_STREAM") {
        const log: HermesLog = {
          task_id: ev.task_id,
          agent_id: ev.agent_id,
          ...ev.payload,
        };
        setLogs((prev) => [log, ...prev].slice(0, 100)); // Keep last 100 logs
      }
    };

    hermesManager.on("PRESENCE_UPDATE", handler);
    hermesManager.on("LOG_STREAM", handler);
    
    const timer = setInterval(() => setIsConnected(hermesManager.connected), 2000);

    return () => {
      hermesManager.off("PRESENCE_UPDATE", handler);
      hermesManager.off("LOG_STREAM", handler);
      clearInterval(timer);
    };
  }, [teamId]);

  return { presence, logs, isConnected };
}
