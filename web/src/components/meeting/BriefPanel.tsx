"use client";

import { useState } from "react";
import type { MeetingBrief, MeetingPhase } from "@/hooks/useMeeting";
import { api } from "@/lib/api";

interface Props {
  brief: MeetingBrief;
  phase: MeetingPhase;
  roomId: string;
}

function BriefTask({ task }: { task: MeetingBrief["tasks"][number] }) {
  const roleColors: Record<string, string> = {
    FE: "#60A5FA", BE: "#34D399", QA: "#A78BFA",
  };
  const color = task.required_role ? (roleColors[task.required_role] ?? "#888") : "#888";
  return (
    <div className="flex items-start gap-2 py-1.5">
      <span
        className="mt-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded text-black/80 shrink-0"
        style={{ backgroundColor: color }}
      >
        {task.required_role ?? "ANY"}
      </span>
      <div className="min-w-0">
        <p className="text-[13px] text-text-primary">{task.subject}</p>
        {task.required_persona && (
          <p className="text-[11px] text-text-muted">페르소나: {task.required_persona}</p>
        )}
      </div>
    </div>
  );
}

export function BriefPanel({ brief, phase, roomId }: Props) {
  const [revising, setRevising] = useState(false);
  const [feedback, setFeedback] = useState("");

  const isLocked = phase === "EXECUTING" || phase === "DONE";

  async function handleConfirm() {
    await api.chat.send("진행해줘", roomId);
  }

  async function handleRevise() {
    if (!feedback.trim()) return;
    await api.chat.send(feedback.trim(), roomId);
    setFeedback("");
    setRevising(false);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-medium text-text-muted uppercase tracking-widest">
          Brief
        </p>
        {isLocked && (
          <span className="text-[10px] text-status-working font-medium">
            {phase === "EXECUTING" ? "진행 중" : "완료"}
          </span>
        )}
      </div>

      {/* Title */}
      <div className="px-3 py-2 rounded-md bg-bg-elevated border border-border-subtle">
        <p className="text-[13px] font-semibold text-text-primary">{brief.title}</p>
      </div>

      {/* Brief markdown (simple whitespace-preserving) */}
      {brief.brief && (
        <div className="px-3 py-2.5 rounded-md bg-bg-elevated border border-border-subtle max-h-40 overflow-y-auto">
          <p className="text-[12px] text-text-secondary whitespace-pre-wrap leading-relaxed">
            {brief.brief}
          </p>
        </div>
      )}

      {/* Task list */}
      {brief.tasks.length > 0 && (
        <div className="px-3 py-2 rounded-md bg-bg-elevated border border-border-subtle">
          <p className="text-[11px] text-text-muted mb-1.5">작업 목록 ({brief.tasks.length}개)</p>
          <div className="divide-y divide-border-subtle">
            {brief.tasks.map((t, i) => (
              <BriefTask key={i} task={t} />
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      {!isLocked && (
        <>
          {!revising ? (
            <div className="flex gap-2">
              <button
                onClick={handleConfirm}
                className="flex-1 py-2 rounded-md bg-accent text-white text-[13px] font-medium hover:bg-accent-hover transition-colors"
              >
                확인 — 시작
              </button>
              <button
                onClick={() => setRevising(true)}
                className="flex-1 py-2 rounded-md border border-border-subtle text-text-secondary text-[13px] hover:bg-bg-hover/50 transition-colors"
              >
                수정 요청
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="수정 사항을 입력하세요..."
                className="w-full bg-bg-elevated border border-border rounded-md px-3 py-2 text-[12px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent/50 resize-none"
                rows={3}
              />
              <div className="flex gap-2">
                <button
                  onClick={handleRevise}
                  className="flex-1 py-1.5 rounded-md bg-accent text-white text-[12px] font-medium hover:bg-accent-hover transition-colors"
                >
                  전달
                </button>
                <button
                  onClick={() => { setRevising(false); setFeedback(""); }}
                  className="flex-1 py-1.5 rounded-md border border-border-subtle text-text-secondary text-[12px] hover:bg-bg-hover/50 transition-colors"
                >
                  취소
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {phase === "EXECUTING" && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-status-working/10 border border-status-working/20">
          <span className="w-2 h-2 rounded-full bg-status-working animate-pulse shrink-0" />
          <p className="text-[12px] text-status-working">에이전트가 작업 중입니다</p>
        </div>
      )}

      {phase === "DONE" && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-status-done/10 border border-status-done/20">
          <span className="text-status-done text-sm">✓</span>
          <p className="text-[12px] text-status-done">모든 작업이 완료되었습니다</p>
        </div>
      )}
    </div>
  );
}
