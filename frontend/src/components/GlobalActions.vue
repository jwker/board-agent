<template>
  <div class="global-actions">
    <el-button
      v-if="showHome"
      :icon="HomeFilled"
      circle
      title="回到主页"
      @click="router.push('/')"
    />
    <el-button
      :icon="Setting"
      circle
      title="全局设置"
      @click="router.push('/settings')"
    />
    <NotificationButton title="通知" />
  </div>
</template>

<script setup lang="ts">
import { HomeFilled, Setting } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import NotificationButton from "./NotificationButton.vue";

withDefaults(defineProps<{ showHome?: boolean }>(), {
  showHome: true,
});

const router = useRouter();
</script>

<style scoped>
.global-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.global-actions .el-button + .el-button {
  margin-left: 0;
}
@media (max-width: 768px) {
  .global-actions {
    display: none;
  }
}
</style>
