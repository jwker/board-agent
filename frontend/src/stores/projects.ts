/** 项目 store：列表加载、新建、归档/恢复。 */

import { defineStore } from "pinia";
import { ref } from "vue";

import {
  createProject,
  listProjects,
  updateProjectStatus,
  type Project,
  type ProjectCreate,
} from "@/api/projects";

export const useProjectsStore = defineStore("projects", () => {
  const projects = ref<Project[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchProjects() {
    loading.value = true;
    error.value = null;
    try {
      projects.value = await listProjects(true);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "加载失败";
    } finally {
      loading.value = false;
    }
  }

  async function addProject(body: ProjectCreate): Promise<Project> {
    const project = await createProject(body);
    projects.value.unshift(project);
    return project;
  }

  async function toggleArchive(project: Project): Promise<void> {
    const next = project.status === "active" ? "archived" : "active";
    const updated = await updateProjectStatus(project.id, next);
    const idx = projects.value.findIndex((p) => p.id === project.id);
    if (idx !== -1) projects.value[idx] = updated;
  }

  return { projects, loading, error, fetchProjects, addProject, toggleArchive };
});
