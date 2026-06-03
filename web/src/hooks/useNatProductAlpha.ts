"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type CommandProposal, type WorkerCommand, type WorkerInfo } from "@/lib/api";
import { wsManager } from "@/lib/ws";

const INVALIDATION_EVENTS = [
  "message.created",
  "proposal.created",
  "proposal.rejected",
  "command.queued",
  "command.leased",
  "command.running",
  "command.completed",
  "command.failed",
  "worker.updated",
  "run.updated",
];

export function useNatProductAlpha(roomId?: string) {
  const [proposals, setProposals] = useState<CommandProposal[]>([]);
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [commands, setCommands] = useState<WorkerCommand[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const [proposalRows, workerRows, commandRows] = await Promise.all([
        api.proposals.list({ roomId, state: "proposed" }),
        api.workers.list(),
        api.commands.list(),
      ]);
      setProposals(proposalRows);
      setWorkers(workerRows);
      setCommands(commandRows);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [roomId]);

  useEffect(() => {
    void refetch();
    const timer = setInterval(refetch, 20_000);
    return () => clearInterval(timer);
  }, [refetch]);

  useEffect(() => {
    const handler = () => void refetch();
    for (const eventType of INVALIDATION_EVENTS) wsManager.on(eventType, handler);
    return () => {
      for (const eventType of INVALIDATION_EVENTS) wsManager.off(eventType, handler);
    };
  }, [refetch]);

  const createProposal = useCallback(async (body: {
    intent: string;
    provider?: string;
    workspace_root?: string;
    acceptance?: Array<Record<string, unknown>>;
  }) => {
    if (!roomId) throw new Error("Room is not ready");
    const proposal = await api.proposals.create({
      room_id: roomId,
      proposed_by: "user://web",
      provider: body.provider ?? "claude",
      workspace_root: body.workspace_root ?? "",
      intent: body.intent,
      acceptance: body.acceptance ?? [{ type: "artifact_required", artifact_type: "code_patch" }],
    });
    await refetch();
    return proposal;
  }, [refetch, roomId]);

  const confirmProposal = useCallback(async (proposalId: string) => {
    const command = await api.proposals.confirm(proposalId);
    await refetch();
    return command;
  }, [refetch]);

  const rejectProposal = useCallback(async (proposalId: string) => {
    const proposal = await api.proposals.reject(proposalId);
    await refetch();
    return proposal;
  }, [refetch]);

  return {
    proposals,
    workers,
    commands,
    loading,
    error,
    refetch,
    createProposal,
    confirmProposal,
    rejectProposal,
  };
}
