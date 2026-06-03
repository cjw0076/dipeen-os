"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { useChat, type ChatMessage } from "@/hooks/useChat";
import { useMeeting, type MeetingPhase, type MeetingMode } from "@/hooks/useMeeting";
import { ParticipantPanel } from "./ParticipantPanel";
import { BriefPanel } from "./BriefPanel";
import { api } from "@/lib/api";

// Phase 뱃지 설정
const PHASE_CONFIG: Record<MeetingPhase, { label: string; color: string }> = {
  DISCUSSING: { label: "논의 중", color: "#888" },
  SOLICITING: { label: "팀 의견 수렴", color: "#FBBF24" },
  BRIEF_READY: { label: "브리프 완성", color: "#60A5FA" },
  EXECUTING: { label: "작업 진행 중", color: "#34D399" },
  DONE: { label: "완료", color: "#A78BFA" },
};

const MODE_CONFIG: Record<MeetingMode, { label: string; desc: string; color: string }> = {
  plan:        { label: "Plan",        desc: "논의 → 계획 → 실행",      color: "#60A5FA" },
  brainstorm:  { label: "Brainstorm",  desc: "자유 아이디어 발산",       color: "#FBBF24" },
  review:      { label: "Review",      desc: "코드 리뷰 · 품질 검토",    color: "#34D399" },
  debate:      { label: "Debate",      desc: "아키텍처 의사결정 (ADR)",  color: "#A78BFA" },
};

function ModeSelector({ mode, roomId, disabled }: { mode: MeetingMode; roomId: string; disabled?: boolean }) {
  const modes = Object.entries(MODE_CONFIG) as [MeetingMode, typeof MODE_CONFIG[MeetingMode]][];

  async function switchMode(next: MeetingMode) {
    if (next === mode || disabled) return;
    await api.meeting.setMode(roomId, next);
  }

  return (
    <div className="flex items-center gap-1 bg-bg-elevated rounded-md p-0.5 border border-border-subtle">
      {modes.map(([key, cfg]) => (
        <button
          key={key}
          onClick={() => switchMode(key)}
          disabled={disabled}
          title={cfg.desc}
          className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
            mode === key
              ? "text-black/80"
              : "text-text-muted hover:text-text-secondary disabled:cursor-not-allowed"
          }`}
          style={mode === key ? { backgroundColor: cfg.color } : {}}
        >
          {cfg.label}
        </button>
      ))}
    </div>
  );
}

function PhaseBadge({ phase }: { phase: MeetingPhase }) {
  const cfg = PHASE_CONFIG[phase];
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ backgroundColor: cfg.color }}
      />
      <span className="text-[11px] font-medium" style={{ color: cfg.color }}>
        {cfg.label}
      </span>
    </div>
  );
}

function Avatar({ sender, role, color, type }: { sender: string; role?: string; color: string; type: string }) {
  if (type === "human") {
    return (
      <div className="w-7 h-7 rounded-full bg-bg-elevated flex items-center justify-center text-[11px] font-medium text-text-secondary shrink-0">
        {sender[0]}
      </div>
    );
  }
  return (
    <div
      className="w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-bold text-black/80 shrink-0"
      style={{ backgroundColor: color }}
    >
      {role || sender[0]}
    </div>
  );
}

function MessageRow({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex gap-2.5 group">
      <Avatar sender={msg.sender} role={msg.role} color={msg.color} type={msg.sender_type} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span
            className="text-[13px] font-semibold"
            style={{ color: msg.sender_type === "human" ? "var(--color-text-primary)" : msg.color }}
          >
            {msg.sender}
          </span>
          <span className="text-[11px] text-text-muted opacity-0 group-hover:opacity-100 transition-opacity">
            {msg.timestamp}
          </span>
        </div>
        <p className="text-[13px] text-text-secondary leading-relaxed whitespace-pre-wrap mt-0.5">
          {msg.content}
        </p>
      </div>
    </div>
  );
}

interface Props {
  roomId: string;
}

export function MeetingRoom({ roomId }: Props) {
  const { messages } = useChat(roomId);
  const { phase, mode, brief, participants } = useMeeting(roomId);
  const modeDisabled = phase === "EXECUTING" || phase === "SOLICITING";
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    await api.chat.send(text, roomId);
  }, [input, roomId]);

  // 브레인스토밍 모드에선 brief 패널 숨김 (아이디어 발산에 집중)
  const showBrief = mode === "plan" && brief && (phase === "BRIEF_READY" || phase === "EXECUTING" || phase === "DONE");

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-border-subtle shrink-0 gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-text-muted text-sm shrink-0">🏢</span>
          <span className="text-sm font-medium truncate">meeting / {roomId}</span>
          {messages.length > 0 && (
            <span className="text-[11px] text-status-done shrink-0">● live</span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <ModeSelector mode={mode} roomId={roomId} disabled={modeDisabled} />
          <PhaseBadge phase={phase} />
        </div>
      </div>

      {/* Body: 60/40 split */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Chat feed (60%) */}
        <div className="flex flex-col" style={{ width: "60%" }}>
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center gap-3 pb-8">
                <p className="text-text-muted text-sm">회의를 시작하세요</p>
                <p className="text-text-muted text-[12px] max-w-xs">
                  무엇을 만들고 싶은지 말씀해 주세요. PM 에이전트와 함께 계획을 세우고 팀에게 배정합니다.
                </p>
              </div>
            ) : (
              messages.map((msg) => (
                <MessageRow key={msg.id} msg={msg} />
              ))
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="px-4 pb-4 pt-2 border-t border-border-subtle shrink-0">
            <div className="relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  mode === "brainstorm"
                    ? "아이디어를 던져보세요. 판단 없이 자유롭게..."
                    : phase === "BRIEF_READY"
                    ? "브리프를 확인하고 '진행해줘' 또는 수정 의견을 입력하세요..."
                    : phase === "EXECUTING"
                    ? "작업 진행 중입니다. 질문이 있으면 입력하세요..."
                    : "무엇을 만들고 싶은가요? 자유롭게 이야기하세요..."
                }
                className="w-full bg-bg-elevated border border-border rounded-lg px-3.5 py-2.5 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 transition-colors pr-10"
                onKeyDown={(e) => { if (e.key === "Enter") sendMessage(); }}
              />
              <button
                onClick={sendMessage}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-secondary transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="w-px bg-border-subtle shrink-0" />

        {/* Right: Participants + Brief (40%) */}
        <div className="flex flex-col overflow-y-auto px-4 py-3 gap-6" style={{ width: "40%" }}>
          <ParticipantPanel participants={participants} />
          {showBrief && (
            <BriefPanel brief={brief} phase={phase} roomId={roomId} />
          )}
        </div>
      </div>
    </div>
  );
}
