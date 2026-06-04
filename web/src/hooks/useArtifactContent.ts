"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type ArtifactContent } from "@/lib/api";

export function useArtifactContent(artifactId: string | null, filename?: string) {
  const [content, setContent] = useState<ArtifactContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchContent = useCallback(async () => {
    if (!artifactId) {
      setContent(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setContent(await api.artifacts.content(artifactId, filename));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [artifactId, filename]);

  useEffect(() => {
    void fetchContent();
  }, [fetchContent]);

  return { content, loading, error, refetch: fetchContent };
}
