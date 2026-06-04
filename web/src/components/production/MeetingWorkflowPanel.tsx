"use client";

import { useCallback, useEffect, useState } from "react";
import { CommandComposer } from "@/components/command/CommandComposer";
import { BrandIcon } from "@/components/ui/brand-icons";
import { api } from "@/lib/api";
import type {
  ActionCandidate,
  AssignmentSpec,
  CommandProposal,
  MeetingClosurePacket,
  RoomMessage,
  WorkerCommand,
} from "@/lib/api";

type ToastTone = "ok" | "warn" | "danger";

type MeetingWorkflowPanelProps = {
  readonly assignment: AssignmentSpec;
  readonly onLoopAdvanced: () => Promise<void> | void;
  readonly onToast: (message: string, tone?: ToastTone) => void;
  readonly provider: string;
};

type BusyState = "message" | "summary" | "approve" | "queue" | null;

function cn(...values: Array<string | false | null | undefined>) { return values.filter(Boolean).join(" "); }

function formatTime(value?: string | null) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }) : "-";
}

function shortId(value?: string | null) {
  return value ? value.length > 12 ? value.slice(0, 12) : value : "-";
}

function errorText(error: unknown) { return error instanceof Error ? error.message : String(error); }

function chip(text: string, tone?: string) {
  return (
    <span className={cn("rounded-md border px-2 py-0.5 text-[11px] font-bold", tone ?? "border-[var(--ds-border)] bg-[var(--ds-surface-raised)] text-[var(--ds-text-muted)]")}>
      {text}
    </span>
  );
}

function candidateForApproval(candidate: ActionCandidate, assignment: AssignmentSpec, provider: string): ActionCandidate {
  const scope = {
    ...candidate.scope,
    ...(assignment.repo ? { repo: assignment.repo } : {}),
    ...(assignment.workspace_ref ? { workspace_ref: assignment.workspace_ref } : {}),
  };
  return {
    ...candidate,
    acceptance: candidate.acceptance.length ? candidate.acceptance : [{ type: "artifact_required", artifact_type: "code_patch" }],
    scope,
    suggested_provider: assignment.provider ?? (provider || candidate.suggested_provider),
    suggested_role: assignment.role ?? candidate.suggested_role,
  };
}

function senderTone(message: RoomMessage) {
  if (message.sender.type === "human") return "border-[#dcc3a0] bg-[var(--ds-surface-raised)]";
  if (message.sender.type === "agent") return "border-emerald-100 bg-emerald-50";
  return "border-[var(--ds-border)] bg-[var(--ds-surface-warm)]";
}

export function MeetingWorkflowPanel({
  assignment,
  onLoopAdvanced,
  onToast,
  provider,
}: MeetingWorkflowPanelProps) {
  const [messages, setMessages] = useState<RoomMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [packet, setPacket] = useState<MeetingClosurePacket | null>(null);
  const [busy, setBusy] = useState<BusyState>(null);
  const [proposalsByCandidate, setProposalsByCandidate] = useState<Record<string, CommandProposal>>({});
  const [queuedByCandidate, setQueuedByCandidate] = useState<Record<string, WorkerCommand>>({});

  const fetchMessages = useCallback(async () => {
    const rows = await api.rooms.messages("general");
    setMessages(rows);
  }, []);

  useEffect(() => {
    void fetchMessages().catch((error: unknown) => onToast(errorText(error), "danger"));
  }, [fetchMessages, onToast]);

  const taskCandidates = packet?.task_candidates ?? [];
  const totalFindings = packet ? packet.decisions.length + packet.task_candidates.length + packet.permission_candidates.length + packet.memory_candidates.length + packet.open_questions.length : 0;

  const sendMessage = useCallback(async (text?: string) => {
    const body = (text ?? draft).trim();
    if (!body) return;
    setBusy("message");
    try {
      await api.rooms.postMessage("general", {
        body,
        message_type: "discussion.message",
        sender_id: "user://web",
        sender_type: "human",
      });
      setDraft("");
      await fetchMessages();
      onToast("회의 메시지를 남겼습니다.");
    } catch (error: unknown) {
      onToast(errorText(error), "danger");
    } finally {
      setBusy(null);
    }
  }, [draft, fetchMessages, onToast]);

  const summarizeMeeting = useCallback(async () => {
    setBusy("summary");
    try {
      const nextPacket = await api.rooms.close("general");
      setPacket(nextPacket);
      await onLoopAdvanced();
      onToast(`회의 정리 완료: 작업 후보 ${nextPacket.task_candidates.length}개.`);
    } catch (error: unknown) {
      onToast(errorText(error), "danger");
    } finally {
      setBusy(null);
    }
  }, [onLoopAdvanced, onToast]);

  const approveCandidate = useCallback(async (candidate: ActionCandidate) => {
    setBusy("approve");
    try {
      const proposal = await api.proposals.approveActionCandidate({
        candidate: candidateForApproval(candidate, assignment, provider),
        proposed_by: "user://web",
        room_id: "general",
      });
      setProposalsByCandidate((current) => ({ ...current, [candidate.candidate_id]: proposal }));
      await onLoopAdvanced();
      onToast("작업 후보가 proposal로 승격됐습니다.");
      return proposal;
    } catch (error: unknown) {
      onToast(errorText(error), "danger");
      return null;
    } finally {
      setBusy(null);
    }
  }, [assignment, onLoopAdvanced, onToast, provider]);

  const queueCandidate = useCallback(async (candidate: ActionCandidate) => {
    setBusy("queue");
    try {
      const proposal = proposalsByCandidate[candidate.candidate_id] ?? await approveCandidate(candidate);
      if (!proposal) return;
      const command = await api.proposals.confirm(proposal.proposal_id);
      setProposalsByCandidate((current) => ({ ...current, [candidate.candidate_id]: { ...proposal, command_id: command.command_id, state: "confirmed", task_id: command.task_id } }));
      setQueuedByCandidate((current) => ({ ...current, [candidate.candidate_id]: command }));
      await onLoopAdvanced();
      onToast("matching worker가 lease할 command를 큐에 넣었습니다.");
    } catch (error: unknown) {
      onToast(errorText(error), "danger");
    } finally {
      setBusy(null);
    }
  }, [approveCandidate, onLoopAdvanced, onToast, proposalsByCandidate]);

  return (
    <section className="overflow-hidden rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface)] shadow-[var(--ds-shadow-card)]">
      <header className="flex min-h-11 items-center justify-between gap-3 border-b border-[var(--ds-border)] px-4">
        <div className="flex min-w-0 items-center gap-2">
          <BrandIcon className="text-[#b98545]" name="chat" size={16} />
          <h2 className="truncate text-sm font-bold text-[var(--ds-text)]">Meeting Chat & Closure</h2>
        </div>
        {chip(`${messages.length} messages`, "border-blue-200 bg-blue-50 text-blue-700")}
      </header>

      <div className="grid gap-4 p-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
        <div className="min-w-0 space-y-3">
          <div className="max-h-[300px] min-h-[190px] space-y-2 overflow-y-auto rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] p-3">
            {messages.length === 0 && (
              <div className="rounded-lg border border-dashed border-[var(--ds-border)] bg-[var(--ds-surface-raised)] px-4 py-5 text-sm leading-6 text-[var(--ds-text-muted)]">
                회의를 시작하세요. 예: "로그인 UI는 민준이 맡고, 백엔드 API는 수민이 구현하자."
              </div>
            )}
            {messages.map((message) => (
              <article className={cn("rounded-lg border px-3 py-2", senderTone(message))} key={message.message_id}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-bold text-[var(--ds-text-muted)]">{message.sender.type}:{message.sender.id}</span>
                  <span className="text-[11px] text-slate-400">{formatTime(message.created_at)}</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[var(--ds-text)]">{message.body}</p>
              </article>
            ))}
          </div>

          <div className="grid gap-2">
            <CommandComposer
              busy={busy === "message"}
              minRows={3}
              onChange={setDraft}
              onSubmit={(text) => void sendMessage(text)}
              placeholder="/plan, /task, /assign, /run..."
              submitLabel="Send"
              value={draft}
            />
            <div className="flex justify-end">
              <button className="rounded-lg border border-[#d6b98e] bg-[var(--ds-surface-warm)] px-3 py-2 text-xs font-bold text-[#8b5b22] shadow-sm disabled:opacity-60" disabled={busy === "summary"} onClick={() => void summarizeMeeting()} type="button">
                정리하기
              </button>
            </div>
          </div>
        </div>

        <div className="min-w-0 space-y-3">
          <div className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-warm)] p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-bold text-[var(--ds-text)]">Closure Candidates</p>
              {chip(packet ? `${totalFindings} findings` : "not summarized")}
            </div>
            <p className="mt-1 text-xs leading-5 text-[var(--ds-text-muted)]">승인 후 confirm하면 matching worker가 command를 lease합니다.</p>
          </div>

          {packet && taskCandidates.length === 0 && (
            <div className="rounded-lg border border-dashed border-[var(--ds-border)] bg-[var(--ds-surface-warm)] px-4 py-5 text-sm leading-6 text-[var(--ds-text-muted)]">
              작업 후보가 없습니다. 구현/수정/작성 같은 실행 의도를 회의 메시지에 남긴 뒤 다시 정리하세요.
            </div>
          )}

          {taskCandidates.map((candidate) => {
            const proposal = proposalsByCandidate[candidate.candidate_id];
            const command = queuedByCandidate[candidate.candidate_id];
            const commandId = command?.command_id ?? proposal?.command_id;
            return (
              <article className="rounded-lg border border-[var(--ds-border)] bg-[var(--ds-surface-raised)] p-3 shadow-sm" key={candidate.candidate_id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="line-clamp-2 text-sm font-bold text-[var(--ds-text)]">{candidate.title || candidate.intent}</p>
                    <p className="mt-1 font-mono text-[11px] text-slate-400">{shortId(candidate.candidate_id)}</p>
                  </div>
                  {chip(commandId ? "queued" : proposal ? "proposal" : "candidate", commandId ? "border-blue-200 bg-blue-50 text-blue-700" : proposal ? "border-emerald-200 bg-emerald-50 text-emerald-700" : undefined)}
                </div>
                <p className="mt-2 line-clamp-3 text-xs leading-5 text-[var(--ds-text-muted)]">{candidate.intent}</p>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-[var(--ds-text-muted)]">
                  <div><dt className="font-bold text-[var(--ds-text)]">provider</dt><dd>{assignment.provider ?? provider ?? candidate.suggested_provider}</dd></div>
                  <div><dt className="font-bold text-[var(--ds-text)]">role</dt><dd>{assignment.role ?? candidate.suggested_role ?? "pool"}</dd></div>
                  <div><dt className="font-bold text-[var(--ds-text)]">proposal</dt><dd>{shortId(proposal?.proposal_id)}</dd></div>
                  <div><dt className="font-bold text-[var(--ds-text)]">command</dt><dd>{shortId(commandId)}</dd></div>
                </dl>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-2 text-[11px] font-bold text-emerald-700 shadow-sm disabled:opacity-60" disabled={Boolean(proposal) || busy === "approve"} onClick={() => void approveCandidate(candidate)} type="button">
                    Approve candidate
                  </button>
                  <button className="rounded-lg bg-[#b98545] px-2 py-2 text-[11px] font-bold text-white shadow-sm disabled:opacity-60" disabled={Boolean(commandId) || busy === "queue"} onClick={() => void queueCandidate(candidate)} type="button">
                    Queue command
                  </button>
                </div>
              </article>
            );
          })}

          {packet && (
            <div className="grid gap-2 text-xs text-slate-600">
              {packet.memory_candidates.length > 0 && <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">Memory candidates: {packet.memory_candidates.length}</div>}
              {packet.permission_candidates.length > 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">Permission candidates: {packet.permission_candidates.length}</div>}
              {packet.open_questions.length > 0 && <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">Open questions: {packet.open_questions.length}</div>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
