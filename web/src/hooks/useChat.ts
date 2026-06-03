"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";
import { getUserName } from "./useUserProfile";
import { EventBus } from "@/game/EventBus";

export interface ChatMessage {
  id: string;
  sender: string;
  sender_type: "human" | "user" | "pm" | "agent" | "question";
  role?: string;
  color: string;
  content: string;
  text?: string;      // backend uses "text" field
  timestamp: string;
  task_id?: string;   // K-2: 질문 카드에서 어떤 태스크에 대한 질문인지
  metadata_json?: Record<string, unknown>;  // W-1: 구조화된 활동 메타데이터
}

function nowTimestamp() {
  return new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

export function useChat(roomId = "general") {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // Load history on mount
  useEffect(() => {
    api.chat.history(roomId).then((hist) => {
      setMessages(hist.map((m: Record<string, unknown>) => ({
        id: m.id as string,
        sender: m.sender as string,
        sender_type: m.sender_type as ChatMessage["sender_type"],
        color: m.color as string,
        content: m.text as string,
        timestamp: m.timestamp as string,
        task_id: (m.task_id as string) || undefined,
        metadata_json: (m.metadata_json as Record<string, unknown>) || undefined,
      })));
    }).catch(() => {
      // Silently fail — WS will still work for new messages
    });
  }, [roomId]);

  // Real-time WS messages
  useEffect(() => {
    const chatHandler = (e: WSEvent) => {
      const ev = e as unknown as Record<string, unknown>;
      // Filter by room_id — ignore messages from other rooms
      if (ev.room_id && ev.room_id !== roomId) return;
      const id = (ev.id as string) || `ws-${Date.now()}`;
      setMessages((prev) => {
        if (prev.some((m) => m.id === id)) return prev;
        return [...prev, {
          id,
          sender: (ev.sender as string) || "unknown",
          sender_type: ((ev.sender_type as string) || "agent") as ChatMessage["sender_type"],
          color: (ev.color as string) || "#888888",
          content: (ev.text as string) || (ev.content as string) || "",
          timestamp: nowTimestamp(),
          task_id: (ev.task_id as string) || undefined,
          metadata_json: (ev.metadata_json as Record<string, unknown>) || undefined,
        }];
      });
      // K-1: 에이전트 메시지 → 게임 캔버스 브리지
      const senderType = (ev.sender_type as string) || "agent";
      if (senderType === "agent") {
        const role = (ev.role as string) || "";
        const content = (ev.text as string) || (ev.content as string) || "";
        if (role && content) {
          EventBus.emit("agent-speech",       { agentId: role, text: content });
          EventBus.emit("agent-last-message", { agentId: role, message: content });
        }
      }
    };
    wsManager.on("chat_message", chatHandler);
    return () => wsManager.off("chat_message", chatHandler);
  }, [roomId]);

  // C-5: A2A 메시지를 채팅방에 표시
  useEffect(() => {
    const agentMsgHandler = (e: WSEvent) => {
      const ev = e as unknown as {
        id: string;
        from_agent: string;
        to_agent: string;
        message_type: string;
        content: string;
      };
      const msgType = ev.message_type.toUpperCase();
      setMessages((prev) => {
        if (prev.some((m) => m.id === ev.id)) return prev;
        return [...prev, {
          id: ev.id || `a2a-${Date.now()}`,
          sender: `${ev.from_agent} → ${ev.to_agent}`,
          sender_type: "agent",
          color: "#888888",
          content: `[${msgType}] ${ev.content}`,
          timestamp: nowTimestamp(),
        }];
      });
    };
    wsManager.on("agent_message", agentMsgHandler);
    return () => wsManager.off("agent_message", agentMsgHandler);
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    const id = `local-${Date.now()}`;

    // Optimistic: show immediately with user's display name
    const displayName = getUserName();
    const optimistic: ChatMessage = {
      id,
      sender: displayName,
      sender_type: "human",
      color: "#FAFAFA",
      content: text,
      timestamp: nowTimestamp(),
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      await api.chat.send(text, roomId, displayName);
    } catch {
      // Message stays visible locally even if API is unreachable
    }
  }, [roomId]);

  return { messages, sendMessage };
}
