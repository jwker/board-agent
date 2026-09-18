<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowRight, MoreFilled, Plus } from "@element-plus/icons-vue";

import { useProjectsStore } from "@/stores/projects";
import type { Project } from "@/api/projects";

const router = useRouter();
const store = useProjectsStore();

const activeProjects = computed(() => store.projects.filter((p) => p.status === "active"));
const archivedProjects = computed(() => store.projects.filter((p) => p.status === "archived"));

onMounted(() => {
  store.fetchProjects();
});

function enterBoard(project: Project) {
  if (project.status === "archived") return; // 归档项目不可进入（仅可恢复）
  router.push(`/projects/${project.id}/board`);
}

async function restore(project: Project) {
  try {
    await store.toggleArchive(project);
    ElMessage.success(`已恢复「${project.name}」`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "操作失败");
  }
}

async function archive(project: Project) {
  try {
    await ElMessageBox.confirm(
      `归档后该项目不参与自动领取、不可进入看板，但可随时恢复。确定归档「${project.name}」？`,
      "归档项目",
      { type: "warning", confirmButtonText: "归档", cancelButtonText: "取消" },
    );
  } catch {
    return; // 用户取消
  }
  try {
    await store.toggleArchive(project);
    ElMessage.success(`已归档「${project.name}」`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "操作失败");
  }
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚活跃";
  if (min < 60) return `${min} 分钟前活跃`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours} 小时前活跃`;
  const days = Math.floor(hours / 24);
  return `${days} 天前活跃`;
}

function archivedDate(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN");
}
</script>

<template>
  <div class="home">
    <div class="home-head">
      <div>
        <h1 class="title">我的项目</h1>
        <p class="subtitle">点击项目进入看板 · 自动领取等设置按项目独立</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="router.push('/projects/new')">新建项目</el-button>
    </div>

    <el-skeleton :loading="store.loading" animated :rows="3">
      <template #default>
        <el-alert
          v-if="store.error"
          :title="store.error"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        />

        <div v-if="activeProjects.length" class="project-grid">
          <el-card
            v-for="p in activeProjects"
            :key="p.id"
            shadow="hover"
            class="project-card"
            @click="enterBoard(p)"
          >
            <div class="card-top">
              <span class="project-name">{{ p.name }}</span>
              <div class="card-actions">
                <el-tag size="small" type="success" effect="light">使用中</el-tag>
                <el-dropdown trigger="click" @command="(cmd: string) => cmd === 'archive' && archive(p)">
                  <el-button class="more-btn" text :icon="MoreFilled" size="small" @click.stop />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="archive">归档项目</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
            <div class="project-dir">{{ p.directory || "未配置授权目录" }}</div>
            <div class="project-stats">
              <div class="stat">
                <span class="stat-num">{{ p.stats?.total ?? 0 }}</span>
                <span class="stat-label">卡片</span>
              </div>
              <div class="stat">
                <span class="stat-num">{{ p.stats?.in_progress ?? 0 }}</span>
                <span class="stat-label">进行中</span>
              </div>
              <div class="stat">
                <span class="stat-num">{{ p.stats?.done ?? 0 }}</span>
                <span class="stat-label">已完成</span>
              </div>
            </div>
            <div class="card-foot">
              <span class="active-time">{{ relativeTime(p.updated_at) }}</span>
              <el-icon class="enter-icon"><ArrowRight /></el-icon>
            </div>
          </el-card>
        </div>

        <template v-if="archivedProjects.length">
          <div class="section-title">已归档</div>
          <p class="archived-note">不参与自动领取 · 不可进入 · 可恢复</p>
          <div class="archived-list">
            <div v-for="p in archivedProjects" :key="p.id" class="archived-item">
              <div class="archived-info">
                <span class="archived-name">{{ p.name }}</span>
                <span class="archived-dir">{{ p.directory || "未配置授权目录" }}</span>
                <span class="archived-date">归档于 {{ archivedDate(p.updated_at) }}</span>
              </div>
              <el-button size="small" @click="restore(p)">恢复</el-button>
            </div>
          </div>
        </template>

        <el-empty
          v-if="store.projects.length === 0"
          description="还没有项目，点击右上角「新建项目」开始"
        />
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.home-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.title {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  margin: 0;
}
.subtitle {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.project-card {
  cursor: pointer;
}
.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.more-btn {
  color: #909399;
}
.project-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-dir {
  font-size: 12px;
  color: #909399;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  margin: 10px 0 14px;
  padding: 6px 10px;
  background: #f5f7fa;
  border-radius: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-stats {
  display: flex;
  gap: 24px;
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stat-num {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
}
.stat-label {
  font-size: 12px;
  color: #909399;
}
.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f2f5;
}
.active-time {
  font-size: 12px;
  color: #909399;
}
.enter-icon {
  color: #c0c4cc;
  font-size: 16px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #606266;
  margin-top: 8px;
}
.archived-note {
  font-size: 12px;
  color: #909399;
  margin: 6px 0 12px;
}
.archived-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.archived-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
}
.archived-info {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  min-width: 0;
}
.archived-name {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}
.archived-dir {
  font-size: 12px;
  color: #909399;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.archived-date {
  font-size: 12px;
  color: #c0c4cc;
}
</style>
