"use client";

import { useState, useEffect, useCallback } from "react";
import { api, type Task } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export function useTasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      const data = await api.tasks.list();
      setTasks(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch + 30s polling fallback
  useEffect(() => {
    fetchTasks();
    const timer = setInterval(fetchTasks, 30_000);
    return () => clearInterval(timer);
  }, [fetchTasks]);

  // Real-time WS updates
  useEffect(() => {
    const handler = (e: WSEvent) => {
      const ev = e as unknown as { task_id: string; status: string; pr_url?: string };
      setTasks((prev) =>
        prev.map((t) =>
          t.task_id === ev.task_id
            ? { ...t, status: ev.status, pr_url: ev.pr_url ?? t.pr_url }
            : t
        )
      );
      // New task event: refetch to get full object
      if (ev.status === "pending") {
        fetchTasks();
      }
    };
    wsManager.on("task_update", handler);
    return () => wsManager.off("task_update", handler);
  }, [fetchTasks]);

  const createTask = useCallback(async (
    subject: string,
    prompt: string,
    options?: { required_role?: string; required_skills?: string[] },
  ) => {
    const task = await api.tasks.create(subject, prompt, options);
    setTasks((prev) => [task, ...prev]);
    return task;
  }, []);

  const cancelTask = useCallback(async (taskId: string) => {
    await api.tasks.cancel(taskId);
    setTasks((prev) =>
      prev.map((t) => (t.task_id === taskId ? { ...t, status: "cancelled" } : t))
    );
  }, []);

  const retryTask = useCallback(async (taskId: string) => {
    await api.tasks.retry(taskId);
    setTasks((prev) =>
      prev.map((t) => (t.task_id === taskId ? { ...t, status: "pending", assigned_agent_id: null } : t))
    );
  }, []);

  return { tasks, loading, error, refetch: fetchTasks, createTask, cancelTask, retryTask };
}
