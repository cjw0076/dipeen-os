"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Project } from "@/lib/api";
import { wsManager, type WSEvent } from "@/lib/ws";

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const [projectList, current] = await Promise.all([
        api.projects.list(),
        api.projects.current(),
      ]);
      setProjects(projectList);
      setCurrentProject(current);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  useEffect(() => {
    const handler = (event: WSEvent) => {
      const projectId = event.project_id as string | undefined;
      if (!projectId) {
        refetch();
        return;
      }
      setProjects((prev) =>
        prev.map((project) =>
          project.id === projectId
            ? {
                ...project,
                name: (event.name as string) || project.name,
                status: (event.status as string) || project.status,
                room_id: (event.room_id as string) || project.room_id,
              }
            : project
        )
      );
      setCurrentProject((project) =>
        project?.id === projectId
          ? {
              ...project,
              name: (event.name as string) || project.name,
              status: (event.status as string) || project.status,
              room_id: (event.room_id as string) || project.room_id,
            }
          : project
      );
    };
    wsManager.on("project_update", handler);
    return () => wsManager.off("project_update", handler);
  }, [refetch]);

  const bootstrapProject = useCallback(async (body: {
    team_name?: string;
    project_name?: string;
    repository_url?: string;
    description?: string;
  }) => {
    const project = await api.projects.bootstrap(body);
    setCurrentProject(project);
    setProjects((prev) => {
      const rest = prev.filter((item) => item.id !== project.id);
      return [project, ...rest];
    });
    return project;
  }, []);

  return { projects, currentProject, loading, error, refetch, bootstrapProject };
}
