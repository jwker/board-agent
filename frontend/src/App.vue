<script setup lang="ts">
import { Bell, FolderOpened, Menu, MoreFilled, Plus, Setting } from "@element-plus/icons-vue";
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import type { Project } from "./api/projects";
import { useNoticeStore } from "./stores/notices";
import { useProjectsStore } from "./stores/projects";

const router = useRouter();
const route = useRoute();
const { unreadCount, drawerOpen, notices, loading, categoryLabel, openDrawer, closeDrawer, readOne, readAll, setupWS } =
  useNoticeStore();
const projectStore = useProjectsStore();

const isMobile = ref(false);
const navOpen = ref(false);

function isProjectActive(projectId: number): boolean {
  return route.path.startsWith(`/projects/${projectId}`);
}

function goProject(p: Project): void {
  if (p.status === "archived") {
    ElMessage.warning("归档项目不可进入，可在首页恢复");
    return;
  }
  navOpen.value = false;
  router.push(`/projects/${p.id}/board`);
}

async function onProjectCommand(cmd: string, p: Project): Promise<void> {
  if (cmd === "archive") {
    try {
      await ElMessageBox.confirm(
        `归档后该项目不参与自动领取、不可进入看板，但可随时恢复。确定归档「${p.name}」？`,
        "归档项目",
        { type: "warning", confirmButtonText: "归档", cancelButtonText: "取消" },
      );
    } catch {
      return; // 用户取消
    }
  }
  try {
    await projectStore.toggleArchive(p);
    ElMessage.success(cmd === "archive" ? `已归档「${p.name}」` : `已恢复「${p.name}」`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "操作失败");
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function onNoticeJump(e: Event): void {
  const { projectId, cardId } = (e as CustomEvent).detail;
  if (projectId && cardId) {
    closeDrawer();
    router.push(`/projects/${projectId}/board/cards/${cardId}`);
  }
}

function clickNotice(n: (typeof notices.value)[number]): void {
  readOne(n);
  if (n.card_id) {
    closeDrawer();
    router.push(`/projects/${n.project_id}/board/cards/${n.card_id}`);
  }
}

onMounted(() => {
  const mq = window.matchMedia("(max-width: 767px)");
  isMobile.value = mq.matches;
  mq.addEventListener("change", (e) => {
    isMobile.value = e.matches;
  });
  projectStore.fetchProjects();
  const teardown = setupWS();
  window.addEventListener("notice-jump", onNoticeJump);
  window.addEventListener("beforeunload", teardown);
});
onBeforeUnmount(() => {
  window.removeEventListener("notice-jump", onNoticeJump);
});
</script>

<template>
  <div class="app-layout">
    <main class="app-main">
      <RouterView :key="route.fullPath" />
    </main>

    <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="sidebar-fab-badge">
      <el-button class="sidebar-fab" :icon="Menu" circle title="导航" @click="navOpen = true" />
    </el-badge>

    <el-drawer v-model="navOpen" direction="ltr" size="240px" :with-header="false" class="nav-drawer">
      <div class="drawer-body">
        <div class="nav-menu">
          <div class="nav-menu-item" @click="navOpen = false; router.push('/')">
            <el-icon><FolderOpened /></el-icon>
            <span>项目列表</span>
          </div>
          <div class="nav-menu-item" @click="navOpen = false; openDrawer()">
            <el-icon><Bell /></el-icon>
            <span>通知</span>
            <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="nav-badge" />
          </div>
          <div class="nav-menu-item" @click="navOpen = false; router.push('/settings')">
            <el-icon><Setting /></el-icon>
            <span>设置</span>
          </div>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="drawerOpen" title="通知中心" size="380px" :close-on-click-modal="true">
      <div class="notice-toolbar">
        <span class="notice-summary">未读 {{ unreadCount }} 条</span>
        <el-button link type="primary" :disabled="unreadCount === 0" @click="readAll()">全部已读</el-button>
      </div>
      <div v-loading="loading" class="notice-list">
        <el-empty v-if="!loading && notices.length === 0" description="暂无通知" :image-size="60" />
        <div
          v-for="n in notices"
          :key="n.id"
          class="notice-item"
          :class="{ unread: !n.read }"
          @click="clickNotice(n)"
        >
          <div class="notice-head">
            <el-tag size="small" effect="plain" type="info">{{ categoryLabel(n.category) }}</el-tag>
            <span class="notice-time">{{ formatTime(n.created_at) }}</span>
          </div>
          <div class="notice-content">{{ n.content }}</div>
          <span v-if="!n.read" class="dot" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
body {
  font-family:
    -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  background: #f5f6f8;
  color: #1f2329;
}
</style>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 16px 16px 12px;
}
.brand-mark {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  background: #409eff;
  border-radius: 6px;
  padding: 4px 8px;
  flex-shrink: 0;
}
.brand-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-section {
  flex: 1;
  overflow-y: auto;
  padding: 4px 10px 12px;
}
.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 4px;
}
.sidebar-title {
  font-size: 12px;
  font-weight: 500;
  color: #909399;
  padding: 6px 8px;
}
.sidebar-add {
  color: #909399;
}
.project-right {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.more-btn {
  color: #909399;
  padding: 4px;
}
.sidebar-hint {
  padding: 8px;
  font-size: 13px;
  color: #c0c4cc;
}
.project-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #303133;
  margin-bottom: 2px;
  transition: background 0.15s;
}
.project-item:hover {
  background: #f5f7fa;
}
.project-item.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}
.project-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-archived {
  flex-shrink: 0;
  font-size: 12px;
  color: #909399;
}
.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px;
  border-top: 1px solid #f0f2f5;
}
.notice-badge {
  display: inline-flex;
}
.app-main {
  flex: 1;
  min-width: 0;
  padding: 24px;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
}
@media (max-width: 768px) {
  .app-main {
    padding: 16px 12px;
  }
}
.sidebar-fab-badge {
  position: fixed;
  left: 12px;
  bottom: 16px;
  z-index: 40;
  display: none;
}
.sidebar-fab {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}
.nav-menu {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nav-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #303133;
  transition: background 0.15s;
}
.nav-menu-item:hover {
  background: #f5f7fa;
}
.nav-badge {
  margin-left: auto;
}
.drawer-body {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.notice-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.notice-summary {
  font-size: 13px;
  color: #909399;
}
.notice-list {
  min-height: 120px;
}
.notice-item {
  position: relative;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.notice-item:hover {
  background: #f5f7fa;
}
.notice-item.unread {
  background: #ecf5ff;
}
.notice-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.notice-time {
  font-size: 12px;
  color: #c0c4cc;
}
.notice-content {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.5;
  color: #303133;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.dot {
  position: absolute;
  top: 14px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f56c6c;
}

/* 移动端显示悬浮球（基础规则在后，此规则须在其后以覆盖 display:none） */
@media (max-width: 768px) {
  .sidebar-fab-badge {
    display: block;
  }
}
</style>
