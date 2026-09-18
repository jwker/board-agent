/** 项目 API 与类型。 */

import { api } from "./client";

export interface ProjectStats {
  total: number;
  in_progress: number;
  done: number;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  directory: string | null;
  directory_status: string | null;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  stats?: ProjectStats;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  directory?: string | null;
  directory_status?: "existing" | "empty" | null;
  agent_md?: string | null;
}

export function listProjects(includeArchived = true): Promise<Project[]> {
  return api.get<Project[]>(`/api/projects?include_archived=${includeArchived}`);
}

export function getProject(id: number): Promise<Project> {
  return api.get<Project>(`/api/projects/${id}`);
}

export function createProject(body: ProjectCreate): Promise<Project> {
  return api.post<Project>("/api/projects", body);
}

export function updateProjectStatus(id: number, status: "active" | "archived"): Promise<Project> {
  return api.patch<Project>(`/api/projects/${id}`, { status });
}
