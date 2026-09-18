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
