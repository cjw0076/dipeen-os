"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type PermissionApproveResult, type PermissionRequest } from "@/lib/api";
import { wsManager } from "@/lib/ws";

export function usePermissions(status = "requested") {
  const [permissions, setPermissions] = useState<PermissionRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 마지막 승인 결과(executor_mode/command_id) — UI가 "dry_run · command 대기"를 표시하는 데 사용.
  const [lastApprove, setLastApprove] = useState<PermissionApproveResult | null>(null);

  const refetch = useCallback(async () => {
    try {
      const data = await api.permissions.list(status);
      setPermissions(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    refetch();
    const timer = setInterval(refetch, 30_000);
    return () => clearInterval(timer);
  }, [refetch]);

  useEffect(() => {
    const handler = () => void refetch();
    wsManager.on("permission.requested", handler);
    wsManager.on("permission.updated", handler);
    wsManager.on("permission.executed", handler);     // worker가 receipt 제출 → inbox 갱신
    return () => {
      wsManager.off("permission.requested", handler);
      wsManager.off("permission.updated", handler);
      wsManager.off("permission.executed", handler);
    };
  }, [refetch]);

  const approvePermission = useCallback(async (permissionRequestId: string) => {
    // 응답은 PermissionRequest가 아니라 {permission_id, executor_mode, command_id, ...}. 입력 id로 낙관적 제거.
    const result = await api.permissions.approve(permissionRequestId);
    setPermissions((prev) => prev.filter((item) => item.permission_request_id !== permissionRequestId));
    setLastApprove(result);
    return result;
  }, []);

  const rejectPermission = useCallback(async (permissionRequestId: string) => {
    const updated = await api.permissions.reject(permissionRequestId);
    setPermissions((prev) => prev.filter((item) => item.permission_request_id !== permissionRequestId));
    return updated;
  }, []);

  return { permissions, loading, error, refetch, approvePermission, rejectPermission, lastApprove };
}
