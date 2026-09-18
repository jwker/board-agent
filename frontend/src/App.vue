<script setup lang="ts">
import { Setting } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

const router = useRouter();
const route = useRoute();
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="brand" @click="router.push('/')">
        <span class="brand-mark">看板</span>
        <span class="brand-name">Board Agent</span>
      </div>
      <div class="header-right">
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
.app-main {
  flex: 1;
  padding: 24px;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
}
</style>
