"use client";

import React from "react";
import { type HermesLog } from "@/hooks/useHermes";

interface LogStreamProps {
  logs: HermesLog[];
  filterTaskId?: string;
}

export const LogStream: React.FC<LogStreamProps> = ({ logs, filterTaskId }) => {
  const filteredLogs = filterTaskId 
    ? logs.filter(l => l.task_id === filterTaskId)
    : logs;

  return (
    <div className="flex flex-col h-full bg-black/40 rounded-lg border border-white/10 overflow-hidden font-mono text-xs">
      <div className="bg-white/5 px-3 py-2 border-b border-white/10 flex justify-between items-center">
        <span className="text-white/60 uppercase tracking-wider">Execution Log Stream</span>
        <div className="flex gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-emerald-500/80">LIVE</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
        {filteredLogs.length === 0 ? (
          <div className="text-white/20 italic text-center py-10">Waiting for logs...</div>
        ) : (
          filteredLogs.map((log, i) => (
            <div key={i} className="flex flex-col gap-1 animate-in fade-in slide-in-from-left-2 duration-300">
              <div className="flex items-center gap-2">
                <span className="text-white/30">[{new Date(log.ts).toLocaleTimeString()}]</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${
                  log.level === 'error' ? 'bg-red-500/20 text-red-400' :
                  log.level === 'warn' ? 'bg-amber-500/20 text-amber-400' :
                  'bg-blue-500/20 text-blue-400'
                }`}>
                  {log.level}
                </span>
                <span className="text-indigo-400 font-bold">{log.agent_id}</span>
                {log.task_id && <span className="text-white/40">→ {log.task_id}</span>}
              </div>
              <div className="pl-4 text-white/80 break-words whitespace-pre-wrap">
                {log.text}
              </div>
              {log.changed_files?.length > 0 && (
                <div className="pl-6 flex flex-wrap gap-1 mt-1">
                  {log.changed_files.map(f => (
                    <span key={f} className="text-[10px] text-white/40 border border-white/5 px-1 rounded">
                      📄 {f}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
