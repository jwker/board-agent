<template>
  <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
    <el-button :size="size" :icon="Bell" circle :title="title" @click="openDrawer()" />
  </el-badge>
</template>

<script setup lang="ts">
import { Bell } from "@element-plus/icons-vue";
import { useNoticeStore } from "@/stores/notices";

withDefaults(
  defineProps<{
    size?: "default" | "small" | "large";
    title?: string;
  }>(),
  {
    size: "default",
    title: "通知",
  }
);

const { unreadCount, openDrawer } = useNoticeStore();
</script>
