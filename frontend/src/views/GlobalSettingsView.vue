<script setup lang="ts">
// 全局设置占位：阶段 2.6 实现（大模型 / 向量 / 通知 / SMTP 等）
</script>

<template>
  <div class="settings">
    <el-page-header content="全局设置" @back="$router.push('/')" />

    <el-card shadow="never" class="settings-card">
      <el-empty description="设置中心建设中（阶段 2.6）：大模型设置、向量设置、通知设置、邮件设置" />
    </el-card>
  </div>
</template>

<style scoped>
.settings {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.settings-card {
  border-radius: 10px;
}
</style>
