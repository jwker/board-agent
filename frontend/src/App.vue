<script setup lang="ts">
import { RouterView } from "vue-router";
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <span class="brand">看板 Agent</span>
      <span class="tag">规划 · 开发中</span>
    </header>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f7;
  color: #1f2329;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.topbar {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #e5e6eb;
}
.brand {
  font-size: 15px;
  font-weight: 600;
}
.tag {
  font-size: 12px;
  color: #8a919f;
}
.content {
  flex: 1;
  padding: 24px;
}
</style>
