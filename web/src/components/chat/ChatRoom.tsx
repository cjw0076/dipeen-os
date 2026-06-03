"use client";

import { useRef, useEffect, useState } from "react";
import { useChat, type ChatMessage } from "@/hooks/useChat";
import { useAgents } from "@/hooks/useAgents";
import { ActivityCard } from "./ActivityCard";
import { api } from "@/lib/api";

function QuestionCard({ msg }: { msg: ChatMessage }) {
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(false);

  function submit() {
    if (!answer.trim() || !msg.task_id) return;
    api.tasks.answer(msg.task_id, answer.trim()).catch(() => {});
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <div className="text-[12px] text-status-done opacity-70">✅ 답변이 전달되었습니다.</div>
    );
  }

  return (
    <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 space-y-2">
      <div className="text-yellow-300 text-[12px] font-semibold">❓ 에이전트 질문</div>
      <p className="text-[13px] text-text-secondary leading-relaxed whitespace-pre-wrap">
        {msg.content}
      </p>
      <div className="flex gap-2">
        <input
          className="flex-1 bg-white/10 rounded px-2 py-1.5 text-[13px] text-text-primary outline-none focus:ring-1 focus:ring-yellow-500/50"
          placeholder="답변을 입력하세요..."
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
        />
        <button
          className="bg-yellow-500 text-black px-3 py-1 rounded text-[12px] font-medium disabled:opacity-40 hover:bg-yellow-400 transition-colors"
          disabled={!answer.trim()}
          onClick={submit}
        >
          답변
        </button>
      </div>
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
  // K-2: 질문 메시지는 별도 카드 렌더링
  if (msg.sender_type === "question") {
    return (
      <div className="animate-fade-in pl-2 border-l-2 border-yellow-500/40">
        <div className="flex items-baseline gap-2 mb-1.5">
          <span className="text-[13px] font-semibold" style={{ color: msg.color }}>{msg.sender}</span>
          <span className="text-[11px] text-text-muted">{msg.timestamp}</span>
        </div>
        <QuestionCard msg={msg} />
      </div>
    );
  }

  // W-3: 구조화된 활동 메시지는 ActivityCard로 렌더링
  const meta = msg.metadata_json as Record<string, unknown> | undefined;
  if (meta?.kind) {
    // W-5: 채팅 노이즈 감소 — tool_use는 AgentActivityPanel에서만 표시
    if (meta.kind === "tool_use") return null;
    // progress는 분당 1회만 표시 (60초 이상 간격)
    if (meta.kind === "progress") {
      const elapsed = meta.elapsed_sec as number;
      if (elapsed % 60 >= 15) return null;
    }
    const isToolUse = meta.kind === "tool_use";
    return (
      <div className={`animate-fade-in pl-2 border-l-2 ${isToolUse ? "py-0" : "py-0.5"}`}
        style={{ borderColor: `${msg.color}55` }}
      >
        {!isToolUse && (
          <div className="flex items-baseline gap-2 mb-1">
            <span className="text-[12px] font-semibold" style={{ color: msg.color }}>{msg.sender}</span>
            <span className="text-[10px] text-text-muted">{msg.timestamp}</span>
          </div>
        )}
        <ActivityCard meta={meta as Parameters<typeof ActivityCard>[0]["meta"]} color={msg.color} />
      </div>
    );
  }

  const isAgent = msg.sender_type === "agent" || msg.sender_type === "pm";
  return (
    <div className={`flex gap-2.5 group animate-fade-in ${isAgent ? "pl-2 border-l-2" : ""}`}
      style={isAgent ? { borderColor: `${msg.color}55` } : undefined}
    >
      <Avatar sender={msg.sender} role={msg.role} color={msg.color} type={msg.sender_type} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span
            className="text-[13px] font-semibold"
            style={{ color: msg.sender_type === "human" ? "var(--color-text-primary)" : msg.color }}
          >
            {msg.sender}
          </span>
          {msg.sender_type !== "human" && (
            <span
              className="text-[9px] font-medium px-1 py-px rounded uppercase tracking-wide opacity-60"
              style={{ backgroundColor: `${msg.color}22`, color: msg.color }}
            >
              {msg.sender_type === "pm" ? "PM" : msg.role ?? "agent"}
            </span>
          )}
          <span className="text-[11px] text-text-muted opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
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

function TypingIndicator({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex gap-2.5 pl-2 animate-fade-in" style={{ borderLeft: `2px solid ${color}55` }}>
      <div className="w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-bold text-black/80 shrink-0"
        style={{ backgroundColor: color }}>
        …
      </div>
      <div className="flex items-center gap-2 py-1">
        <span className="text-[12px] font-semibold" style={{ color }}>{label}</span>
        <span className="flex gap-0.5 items-end">
          {[0, 1, 2].map(i => (
            <span key={i} className="w-1 h-1 rounded-full bg-text-muted"
              style={{ animation: `typing 1s ease-in-out ${i * 0.2}s infinite` }} />
          ))}
        </span>
      </div>
    </div>
  );
}

function MemberPanel({ agents }: { agents: { agent_id: string; label: string; role?: string | null; status: string; color: string; current_task_id?: string | null }[] }) {
  const online = agents.filter(a => a.status !== "offline");
  const offline = agents.filter(a => a.status === "offline");

  return (
    <div className="w-48 border-l border-border-subtle flex flex-col shrink-0">
      <div className="h-12 flex items-center px-3 border-b border-border-subtle">
        <span className="text-[11px] font-medium text-text-muted uppercase tracking-widest">Members</span>
        <span className="ml-auto text-[10px] text-text-muted">{online.length} online</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {/* PM Agent (always shown) */}
        <div className="flex items-center gap-2 px-2 py-1.5 rounded-md">
          <div className="w-5 h-5 rounded text-[9px] font-bold flex items-center justify-center text-black/80 bg-[#FBBF24]">PM</div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium truncate">PM Agent</p>
            <p className="text-[9px] text-text-muted">orchestrator</p>
          </div>
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" />
        </div>
        {/* Online agents */}
        {online.map(a => (
          <div key={a.agent_id} className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-bg-elevated/50 transition-colors">
            <div className="w-5 h-5 rounded text-[9px] font-bold flex items-center justify-center text-black/80 shrink-0"
              style={{ backgroundColor: a.color }}>
              {(a.role ?? "?").toUpperCase().slice(0, 2)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium truncate">{a.label}</p>
              <p className="text-[9px] text-text-muted truncate">
                {a.status === "working" && a.current_task_id
                  ? `working: ${a.current_task_id.slice(0, 10)}`
                  : a.status}
              </p>
            </div>
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
              a.status === "working" ? "bg-blue-400 animate-pulse" : "bg-green-500"
            }`} />
          </div>
        ))}
        {/* Offline agents */}
        {offline.length > 0 && (
          <>
            <div className="pt-2 pb-1 px-2">
              <span className="text-[9px] text-text-muted uppercase tracking-wider">Offline</span>
            </div>
            {offline.map(a => (
              <div key={a.agent_id} className="flex items-center gap-2 px-2 py-1.5 opacity-40">
                <div className="w-5 h-5 rounded text-[9px] font-bold flex items-center justify-center text-black/80 shrink-0"
                  style={{ backgroundColor: a.color }}>
                  {(a.role ?? "?").toUpperCase().slice(0, 2)}
                </div>
                <p className="text-[11px] truncate">{a.label}</p>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

export function ChatRoom() {
  const { messages: liveMessages, sendMessage } = useChat();
  const { agents: liveAgents } = useAgents();
  const [input, setInput] = useState("");
  const [showMembers, setShowMembers] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const messages = liveMessages;

  // Agents currently working (show typing indicator)
  const workingAgents = liveAgents.filter((a) => a.status === "working");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, workingAgents.length]);

  function handleSend() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    sendMessage(text);
  }

  return (
    <div className="flex h-full">
    <div className="flex flex-col flex-1 min-w-0">
      {/* Header */}
      <div className="h-12 flex items-center px-4 border-b border-border-subtle shrink-0 gap-3">
        <div className="flex items-center gap-1.5">
          <span className="text-text-muted text-sm">#</span>
          <span className="text-sm font-medium">general</span>
        </div>
        <span className="text-[11px] text-status-done flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-status-done animate-pulse inline-block" />
          live
        </span>
        {/* Members toggle + agent chips */}
        <div className="flex items-center gap-2 ml-auto">
          {liveAgents.filter(a => a.status !== "offline").map((a) => (
            <div
              key={a.agent_id}
              title={`${a.label} — ${a.status}`}
              className="w-5 h-5 rounded text-[9px] font-bold flex items-center justify-center text-black/80"
              style={{ backgroundColor: a.color, opacity: a.status === "idle" ? 0.5 : 1 }}
            >
              {(a.role ?? "?").toUpperCase().slice(0, 2)}
            </div>
          ))}
          <button
            onClick={() => setShowMembers(v => !v)}
            title="Toggle members"
            className={`p-1 rounded transition-colors ${showMembers ? "text-accent" : "text-text-muted hover:text-text-secondary"}`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-1.997M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((msg) => (
          <MessageRow key={msg.id} msg={msg} />
        ))}
        {/* Typing indicators for working agents */}
        {workingAgents.map((a) => (
          <TypingIndicator key={a.agent_id} color={a.color} label={a.label} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-4 shrink-0">
        <div className="relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message #general — /cancel T-001, /status"
            className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-2.5 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/40 transition-all pr-10"
            onKeyDown={(e) => { if (e.key === "Enter") handleSend(); }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-accent disabled:opacity-30 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          </button>
        </div>
      </div>
    </div>
    {showMembers && <MemberPanel agents={liveAgents} />}
    </div>
  );
}
