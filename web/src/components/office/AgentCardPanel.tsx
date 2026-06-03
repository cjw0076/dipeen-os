// web/src/components/office/AgentCardPanel.tsx
// 에이전트 클릭 시 하단에서 슬라이드업되는 80px 카드
// 상태 + 마지막 메시지 + 퀵액션 (💬 채팅, ⛔ 취소, ✕ 닫기)

"use client";

import { useState } from "react";
import type { DipeenAgent } from "./useOfficeEngine";

interface AgentCardPanelProps {
  agent: DipeenAgent | null;
  tokens: number;
  lastMessage: string | null;
  onChat: () => void;
  onCancel: () => void;
  onClose: () => void;
  onSendMessage: (text: string) => void;
}

const STATUS_LABEL: Record<string, string> = {
  working: "작업 중",
  reviewing: "검토 중",
  idle: "대기",
  done: "완료",
  error: "오류",
  offline: "오프라인",
};

const STATUS_DOT_CLASS: Record<string, string> = {
  working:   "bg-[#60A5FA]",
  reviewing: "bg-[#A78BFA]",
  idle:      "bg-zinc-500",
  done:      "bg-[#34D399]",
  error:     "bg-red-400",
  offline:   "bg-zinc-700",
};

export function AgentCardPanel({ agent, tokens, lastMessage, onChat, onCancel, onClose, onSendMessage }: AgentCardPanelProps) {
  const visible = agent !== null;
  const [msgInput, setMsgInput] = useState("");
  const [showInput, setShowInput] = useState(false);

  return (
    <div
      className="absolute bottom-0 left-0 right-0 z-20 transition-transform duration-300 ease-out"
      style={{ transform: visible ? "translateY(0)" : "translateY(100%)" }}
    >
      {agent && (
        <div className="relative h-20 bg-bg-card border-t border-border flex items-center gap-3 px-4 shadow-2xl shadow-black/60">
          {/* 아바타 + 상태 점 */}
          <div className="flex flex-col items-center gap-1 shrink-0">
            <div
              className="w-9 h-9 rounded-full flex items-center justify-center text-[12px] font-bold text-black/80 border-2 border-white/10"
              style={{ backgroundColor: agent.color }}
            >
              {agent.role[0]}
            </div>
            <div className="flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT_CLASS[agent.status] ?? "bg-zinc-500"}`} />
              <span className="text-[10px] text-text-muted">{STATUS_LABEL[agent.status] ?? agent.status}</span>
            </div>
          </div>

          {/* 이름 + 마지막 메시지 */}
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-semibold text-text-primary truncate">{agent.label}</p>
            {lastMessage ? (
              <p className="text-[11px] text-text-muted truncate mt-0.5">&ldquo;{lastMessage}&rdquo;</p>
            ) : agent.task ? (
              <p className="text-[11px] text-text-muted truncate mt-0.5 font-mono">{agent.task}</p>
            ) : (
              <p className="text-[11px] text-text-muted mt-0.5">
                {tokens > 0 ? `${tokens.toLocaleString()} tokens` : "대기 중"}
              </p>
            )}
          </div>

          {/* 퀵 액션 */}
          <div className="flex flex-col gap-1.5 shrink-0">
            <button
              onClick={() => setShowInput(v => !v)}
              className="flex items-center gap-1 px-2.5 py-1 bg-bg-elevated hover:bg-accent/20 text-[11px] text-accent rounded-md transition-colors"
            >
              💬 {showInput ? "닫기" : "메시지"}
            </button>
            {agent.taskId && (
              <button
                onClick={onCancel}
                className="flex items-center gap-1 px-2.5 py-1 bg-bg-elevated hover:bg-red-900/30 text-[11px] text-red-400 rounded-md transition-colors"
              >
                ⛔ 취소
              </button>
            )}
          </div>

          {/* 닫기 */}
          <button
            onClick={onClose}
            className="p-1.5 text-text-muted hover:text-text-primary transition-colors shrink-0"
            aria-label="닫기"
          >
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>

          {showInput && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (msgInput.trim()) {
                  onSendMessage(msgInput.trim());
                  setMsgInput("");
                  setShowInput(false);
                }
              }}
              className="absolute bottom-full left-0 right-0 flex gap-2 px-4 py-2 bg-bg-elevated border-t border-border"
            >
              <input
                autoFocus
                value={msgInput}
                onChange={(e) => setMsgInput(e.target.value)}
                placeholder={`@${agent?.label ?? "에이전트"} 에게...`}
                className="flex-1 bg-bg-card border border-border rounded-md px-3 py-1.5 text-[12px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent/50"
              />
              <button
                type="submit"
                className="px-3 py-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] rounded-md transition-colors"
              >
                전송
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
