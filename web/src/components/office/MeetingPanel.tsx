"use client";

import type { DipeenAgent } from "./useOfficeEngine";

interface MeetingPanelProps {
  agents: DipeenAgent[];
  onRequestMeeting: () => void;
  onClose: () => void;
}

export function MeetingPanel({ agents, onRequestMeeting, onClose }: MeetingPanelProps) {
  if (agents.length === 0) return null;

  return (
    <div className="absolute inset-0 flex items-center justify-center z-30 pointer-events-none">
      <div className="pointer-events-auto bg-bg-card/90 backdrop-blur-sm border border-border rounded-xl px-5 py-4 shadow-2xl shadow-black/60 w-60">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <span className="text-[13px] font-semibold text-text-primary">🏢 회의실</span>
          <button
            onClick={onClose}
            className="p-1 text-text-muted hover:text-text-primary transition-colors"
            aria-label="닫기"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Agents in zone */}
        <div className="flex flex-col gap-2 mb-4">
          {agents.map((agent) => (
            <div key={agent.id} className="flex items-center gap-2">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-black/80 shrink-0"
                style={{ backgroundColor: agent.color }}
              >
                {agent.role[0]}
              </div>
              <span className="text-[12px] text-text-primary">{agent.label}</span>
              <span className="text-[10px] text-text-muted ml-auto">{agent.status}</span>
            </div>
          ))}
        </div>

        {/* Action */}
        <button
          onClick={onRequestMeeting}
          className="w-full py-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium rounded-md transition-colors"
        >
          회의 시작 요청
        </button>
      </div>
    </div>
  );
}
