"use client";

import { useState, useEffect, useCallback } from "react";
import { wsManager, type WSEvent } from "@/lib/ws";
import { api } from "@/lib/api";

export type MeetingPhase = "DISCUSSING" | "SOLICITING" | "BRIEF_READY" | "EXECUTING" | "DONE";

export interface BriefTask {
  subject: string;
  prompt: string;
  required_role?: string | null;
  required_persona?: string | null;
}

export interface MeetingBrief {
  title: string;
  brief: string;
  tasks: BriefTask[];
}

export interface Participant {
  agent_id: string;
  role: string;
  status: string;
  color: string;
  typing: boolean;
}

const ROLE_COLORS: Record<string, string> = {
  FE: "#60A5FA",
  BE: "#34D399",
  QA: "#A78BFA",
  PM: "#FBBF24",
};

export type MeetingMode = "plan" | "brainstorm" | "review" | "debate";

export function useMeeting(roomId: string) {
  const [phase, setPhase] = useState<MeetingPhase>("DISCUSSING");
  const [mode, setMode] = useState<MeetingMode>("plan");
  const [brief, setBrief] = useState<MeetingBrief | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);

  const setMeetingMode = useCallback(async (nextMode: MeetingMode) => {
    setMode(nextMode);
    try {
      await api.meeting.setMode(roomId, nextMode);
    } catch {
      // Keep the optimistic UI state; the next state fetch or WS event will reconcile it.
    }
  }, [roomId]);

  // WS 재연결 복구: 현재 phase/brief/mode 로드
  useEffect(() => {
    api.meeting.getState(roomId)
      .then((s) => {
        if (s.phase) setPhase(s.phase as MeetingPhase);
        if (s.mode) setMode(s.mode as MeetingMode);
        if (s.brief) setBrief(s.brief as unknown as MeetingBrief);
      })
      .catch(() => {});
  }, [roomId]);

  // 참여자 목록: roster에서 로드
  useEffect(() => {
    api.agents.roster()
      .then(({ agents }) => {
        setParticipants(
          agents.map((a) => ({
            agent_id: a.agent_id,
            role: a.role || "?",
            status: a.status,
            color: ROLE_COLORS[a.role || ""] ?? "#888",
            typing: false,
          }))
        );
      })
      .catch(() => {});
  }, []);

  // WS 이벤트 구독
  useEffect(() => {
    const onPhase = (e: WSEvent) => {
      if (e.room_id !== roomId) return;
      setPhase(e.phase as MeetingPhase);
      if (e.brief) setBrief(e.brief as unknown as MeetingBrief);
      // BRIEF_READY 이상 단계: typing 표시 제거
      const p = e.phase as string;
      if (p === "BRIEF_READY" || p === "EXECUTING" || p === "DONE") {
        setParticipants((prev) => prev.map((pt) => ({ ...pt, typing: false })));
      }
    };

    const onMode = (e: WSEvent) => {
      if (e.room_id !== roomId) return;
      setMode(e.mode as MeetingMode);
    };

    const onInputRequest = (e: WSEvent) => {
      if (e.room_id !== roomId) return;
      // SOLICITING 단계: 모든 에이전트 typing 표시
      setParticipants((prev) => prev.map((pt) => ({ ...pt, typing: true })));
    };

    const onAgentInput = (e: WSEvent) => {
      if (e.room_id !== roomId) return;
      setParticipants((prev) =>
        prev.map((pt) =>
          pt.agent_id === (e.agent_id as string) ? { ...pt, typing: false } : pt
        )
      );
    };

    wsManager.on("meeting_phase", onPhase);
    wsManager.on("meeting_mode", onMode);
    wsManager.on("agent_input_request", onInputRequest);
    wsManager.on("agent_input", onAgentInput);

    return () => {
      wsManager.off("meeting_phase", onPhase);
      wsManager.off("meeting_mode", onMode);
      wsManager.off("agent_input_request", onInputRequest);
      wsManager.off("agent_input", onAgentInput);
    };
  }, [roomId]);

  return { phase, mode, brief, participants, setMeetingMode };
}
