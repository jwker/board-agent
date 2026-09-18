<script setup lang="ts">
import { Bell, Setting } from "@element-plus/icons-vue";
import { onBeforeUnmount, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useNoticeStore } from "./stores/notices";

const router = useRouter();
const route = useRoute();
const { unreadCount, drawerOpen, notices, loading, categoryLabel, openDrawer, closeDrawer, readOne, readAll, setupWS } =
  useNoticeStore();

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
    <header class="app-header">
      <div class="brand" @click="router.push('/')">
        <span class="brand-mark">看板</span>
        <span class="brand-name">Board Agent</span>
      </div>
      <div class="header-right">
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="notice-badge">
          <el-button :icon="Bell" circle title="通知中心" @click="openDrawer()" />
        </el-badge>
        <el-button
          v-if="route.path !== '/settings'"
          :icon="Setting"
          circle
          title="全局设置"
          @click="router.push('/settings')"
        />
      </div>
    </header>
    <main class="app-main">
      <RouterView :key="route.fullPath" />
    </main>

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
  flex-direction: column;
}
.app-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e5e6eb;
  position: sticky;
  top: 0;
  z-index: 10;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.brand-mark {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  background: #409eff;
  border-radius: 6px;
  padding: 4px 8px;
}
.brand-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.notice-badge {
  display: inline-flex;
}
.app-main {
  flex: 1;
  padding: 24px;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
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
</style>
