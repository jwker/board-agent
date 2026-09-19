/** 卡片类型标签的统一展示定义（列表 / 详情 / 表单共用，保证全站一致）。 */

import type { CardType } from "@/api/cards";

export const TYPE_LABELS: Record<CardType, string> = {
  requirement: "需求",
  bug: "缺陷",
  refactor: "重构",
  optimize: "优化",
  task: "任务",
  research: "调研",
  doc: "文档",
};

/** 每种类型一个独立色（无灰、不重复）。 */
export const TYPE_COLORS: Record<CardType, string> = {
  requirement: "#409eff", // 蓝
  bug: "#f56c6c", // 红
  refactor: "#e6a23c", // 橙
  optimize: "#67c23a", // 绿
  task: "#9254de", // 紫
  research: "#13c2c2", // 青
  doc: "#f759ab", // 粉
};

/** 返回 el-tag 的自定义浅色样式（light 效果：浅底 + 彩色文字/边框）。 */
export function typeTagStyle(type: CardType): Record<string, string> {
  const c = TYPE_COLORS[type];
  return {
    "--el-tag-bg-color": `${c}1a`,
    "--el-tag-border-color": `${c}59`,
    "--el-tag-text-color": c,
  };
}

// 进行中卡片的 AI 执行状态标签（execution_status）
export const EXECUTION_LABELS: Record<string, string> = {
  queued: "排队中",
  running: "AI 处理中",
  waiting_approval: "等待人工审批",
  completed: "AI 处理完成",
  failed: "AI 处理失败",
  cancelled: "已取消",
};

export function executionTagType(status: string | null): "info" | "primary" | "warning" | "success" | "danger" {
  if (status === "running" || status === "queued") return "primary";
  if (status === "waiting_approval") return "warning";
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  return "info";
}
