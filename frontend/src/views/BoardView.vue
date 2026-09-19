<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, ChatDotRound, FolderOpened, Lock, MoreFilled, Plus, Search } from "@element-plus/icons-vue";
import { VueDraggable } from "vue-draggable-plus";

import { getProject, type Project } from "@/api/projects";
import { onWS } from "@/api/ws";
import { EXECUTION_LABELS, TYPE_LABELS, executionTagType, typeTagStyle } from "@/constants/card";
import {
  type Card,
  type CardStatus,
  type CardType,
  type Priority,
  updateCard,
  archiveCard,
  restoreCard,
} from "@/api/cards";
import { useCardsStore } from "@/stores/cards";
import { useProjectsStore } from "@/stores/projects";
import {
  getAutoClaim,
  saveAutoClaim,
  getProjectModel,
  putProjectModel,
  getLLMSettings,
  type AutoClaimSettings,
  type LLMSettings,
} from "@/api/settings";
import CardFormDialog from "@/components/CardFormDialog.vue";

const props = defineProps<{ projectId: string }>();
const router = useRouter();
const cardsStore = useCardsStore();
const projectsStore = useProjectsStore();

const projectId = Number(props.projectId);
const project = ref<Project | null>(null);
const search = ref("");
const dialogVisible = ref(false);
const editingCard = ref<Card | null>(null);
const createStatus = ref<CardStatus>("backlog");
const archiveVisible = ref(false);
const autoClaim = ref<AutoClaimSettings>({ enabled: false, start_time: "22:00", end_time: "08:00" });
const autoClaimVisible = ref(false);
const projectModel = ref(""); // "provider_id::request"；空串 = 跟随全局默认
const llmSettings = ref<LLMSettings | null>(null);

const modelOptions = computed(() => {
  const opts: { value: string; label: string }[] = [{ value: "", label: "跟随全局默认" }];
  for (const p of llmSettings.value?.providers ?? []) {
    for (const m of p.models) {
      opts.push({ value: `${p.id}::${m.request}`, label: `${p.name} / ${m.display}` });
    }
  }
  return opts;
});

const COLUMNS: { key: CardStatus; label: string; stripe: string }[] = [
  { key: "backlog", label: "积压", stripe: "#c9cdd4" },
  { key: "todo", label: "待办", stripe: "#409eff" },
  { key: "in_progress", label: "进行中", stripe: "#e6a23c" },
  { key: "done", label: "已完成", stripe: "#67c23a" },
];

const allProjects = computed(() => {
  const list = [...projectsStore.projects];
  if (project.value && !list.some((p) => p.id === project.value!.id)) {
    list.unshift(project.value);
  }
  return list.filter((p) => p.status === "active");
});

function switchProject(command: string | number) {
  if (command === "all") {
    router.push("/");
    return;
  }
  const id = Number(command);
  if (id !== projectId) router.push(`/projects/${id}/board`);
}

const PRIORITY_LABELS: Record<Priority, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

onMounted(async () => {
  try {
    project.value = await getProject(projectId);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载项目失败");
  }
  await projectsStore.fetchProjects();
  await cardsStore.fetchCards(projectId);
  try {
    autoClaim.value = await getAutoClaim(projectId);
  } catch {
    /* 配置缺失时用默认值 */
  }
});

function onWsReconnected(): void {
  // WS 重连后全量重拉当前视图（TECH-DESIGN §4 断线补偿）
  cardsStore.fetchCards(projectId);
}

// 卡片更新事件（标题精修 / AI 执行状态）：payload 自带字段，就地更新，避免全量重拉
const offCardUpdated = onWS("card.updated", (msg) => {
  const { card_id, title, execution_status } = msg.payload as {
    card_id?: number;
    title?: string;
    execution_status?: string;
  };
  if (card_id) {
    if (typeof title === "string") cardsStore.updateTitle(card_id, title);
    if (typeof execution_status === "string") cardsStore.updateExecutionStatus(card_id, execution_status);
  }
});

onMounted(() => window.addEventListener("ws-reconnected", onWsReconnected));
onBeforeUnmount(() => {
  window.removeEventListener("ws-reconnected", onWsReconnected);
  offCardUpdated();
});

async function openProjectSettings(): Promise<void> {
  try {
    autoClaim.value = await getAutoClaim(projectId);
  } catch {
    /* 保持默认 */
  }
  try {
    const pm = await getProjectModel(projectId);
    projectModel.value = pm.provider_id && pm.model ? `${pm.provider_id}::${pm.model}` : "";
  } catch {
    projectModel.value = "";
  }
  try {
    llmSettings.value = await getLLMSettings();
  } catch {
    /* 未配置时下拉仅“跟随全局默认” */
  }
  autoClaimVisible.value = true;
}

async function saveProjectSettings(): Promise<void> {
  try {
    autoClaim.value = await saveAutoClaim(projectId, autoClaim.value);
    const [providerId, model] = projectModel.value.split("::");
    await putProjectModel(projectId, { provider_id: providerId ?? "", model: model ?? "" });
    autoClaimVisible.value = false;
    ElMessage.success("项目设置已保存");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  }
}

const cardsByStatus = computed(() => {
  const kw = search.value.trim().toLowerCase();
  const map: Record<string, Card[]> = { backlog: [], todo: [], in_progress: [], done: [], archived: [] };
  for (const card of cardsStore.cards) {
    if (card.status === "archived") continue; // 归档卡不在看板列展示（后续归档区）
    if (kw) {
      const hay = `${card.title} ${card.content} ${(card.custom_tags ?? []).join(" ")}`.toLowerCase();
      if (!hay.includes(kw)) continue;
    }
    (map[card.status] ??= []).push(card);
  }
  return map;
});

/* ---- 拖拽（vue-draggable-plus 跨列移动） ---- */
const columnLists: Record<CardStatus, Ref<Card[]>> = {
  backlog: ref<Card[]>([]),
  todo: ref<Card[]>([]),
  in_progress: ref<Card[]>([]),
  done: ref<Card[]>([]),
  archived: ref<Card[]>([]),
};

function refreshColumns() {
  for (const col of COLUMNS) {
    columnLists[col.key].value = cardsStore.cards.filter((c) => c.status === col.key);
  }
}
watch(() => cardsStore.cards, refreshColumns, { immediate: true, deep: true });

let dragging = false;
function dragStart() {
  dragging = true;
}
function dragEnd() {
  // 拖拽结束后可能还会触发一次 click，延迟清除标志以拦截
  setTimeout(() => {
    dragging = false;
  }, 0);
}
function cardClick(card: Card) {
  if (dragging) return;
  openDetail(card);
}

function onAdd(colKey: CardStatus, evt: { newIndex: number }) {
  const card = columnLists[colKey].value[evt.newIndex];
  if (card) moveCard(card, colKey);
}

function onMoveCommand(card: Card, target: string) {
  if (target === "archive") {
    onArchive(card);
    return;
  }
  moveCard(card, target as CardStatus);
}

/* ---- 归档（用户主动触发，终态；恢复回原列） ---- */
const archivedCards = computed(() =>
  cardsStore.cards.filter((c) => c.status === "archived"),
);

function colLabel(status: string | null | undefined): string {
  return COLUMNS.find((c) => c.key === status)?.label ?? "积压";
}

async function onArchive(card: Card) {
  try {
    await ElMessageBox.confirm(
      `归档「${card.title || "未命名卡片"}」？归档后可随时恢复。`,
      "归档卡片",
      { type: "warning", confirmButtonText: "归档", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  try {
    const updated = await archiveCard(card.id);
    cardsStore.replaceCard(updated);
    ElMessage.success("已归档");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "归档失败");
  }
}

async function onRestore(card: Card) {
  const target = card.archived_from ?? "backlog";
  if (target === "in_progress" || target === "done") {
    try {
      await ElMessageBox.confirm(
        target === "in_progress"
          ? `将恢复到「进行中」：AI 不自动触发，你评论后它才会继续。确定恢复？`
          : `将恢复到「已完成」：卡片保持完成状态，不再重复 AI 收尾。确定恢复？`,
        "恢复卡片",
        { type: "warning", confirmButtonText: "恢复", cancelButtonText: "取消" },
      );
    } catch {
      return;
    }
  }
  try {
    const updated = await restoreCard(card.id);
    cardsStore.replaceCard(updated);
    ElMessage.success(`已恢复到「${colLabel(updated.status)}」`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "恢复失败");
  }
}

async function moveCard(card: Card, target: CardStatus) {
  if (card.status === target) return;
  if (target === "done" || target === "in_progress") {
    try {
      await ElMessageBox.confirm(
        target === "done"
          ? `确定将「${card.title || "未命名卡片"}」标记为已完成？完成后 AI 会总结该卡片。`
          : `确定将「${card.title || "未命名卡片"}」移入进行中？将触发 AI 执行该卡片。`,
        target === "done" ? "标记完成" : "移入进行中",
        { type: "warning", confirmButtonText: "确定", cancelButtonText: "取消" },
      );
    } catch {
      refreshColumns(); // 取消：恢复原列位置
      return;
    }
  }
  try {
    const updated = await updateCard(card.id, { status: target });
    cardsStore.replaceCard(updated);
    ElMessage.success(`已移入「${COLUMNS.find((c) => c.key === target)!.label}」`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "移动失败");
    refreshColumns();
  }
}

/* ---- 新建 / 编辑弹窗（复用 CardFormDialog） ---- */
function openCreate(status: CardStatus = "backlog") {
  editingCard.value = null;
  createStatus.value = status;
  dialogVisible.value = true;
}

function openEdit(card: Card) {
  editingCard.value = card;
  dialogVisible.value = true;
}

function openDetail(card: Card) {
  router.push(`/projects/${projectId}/board/cards/${card.id}`);
}

function dueInDays(due: string): string {
  const diff = Math.ceil((new Date(due).getTime() - Date.now()) / 86400000);
  if (diff < 0) return `已逾期 ${-diff} 天`;
  if (diff === 0) return "今天截止";
  return `剩 ${diff} 天`;
}
</script>

<template>
  <div class="board">
    <div class="board-head">
      <el-dropdown trigger="click" @command="switchProject">
        <div class="project-title">
          <span class="project-name-text">{{ project ? project.name : "看板" }}</span>
          <el-icon class="title-caret"><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="p in allProjects"
              :key="p.id"
              :command="p.id"
              :disabled="p.id === projectId"
            >
              <span :class="{ current: p.id === projectId }">{{ p.name }}</span>
            </el-dropdown-item>
            <el-dropdown-item command="all" divided>全部项目</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <div class="head-actions">
        <el-input
          v-model="search"
          class="search-input"
          :prefix-icon="Search"
          placeholder="搜索卡片…（标题 / 内容 / 标签）"
          clearable
          style="width: 300px"
        />
        <el-button
          class="auto-claim-btn"
          :class="{ on: autoClaim.enabled }"
          @click="openProjectSettings()"
        >
          项目设置{{ autoClaim.enabled ? ` · 自动领取 ${autoClaim.start_time}-${autoClaim.end_time}` : "" }}
        </el-button>
        <el-button :icon="FolderOpened" @click="archiveVisible = true">归档区</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate()">新建卡片</el-button>
      </div>
    </div>

    <div v-if="cardsStore.loading" v-loading="true" class="board-loading" />

    <el-alert
      v-else-if="cardsStore.error"
      :title="cardsStore.error"
      type="error"
      :closable="false"
      show-icon
    />

    <div v-else class="board-columns">
      <div v-for="col in COLUMNS" :key="col.key" class="column">
        <div class="column-head">
          <span class="column-stripe" :style="{ background: col.stripe }"></span>
          <span class="column-label">{{ col.label }}</span>
          <span class="column-count">{{ cardsByStatus[col.key].length }}</span>
        </div>
        <div class="column-body">
          <VueDraggable
            v-model="columnLists[col.key].value"
            class="column-draggable"
            group="cards"
            :animation="150"
            ghost-class="card-ghost"
            :sort="true"
            @start="dragStart"
            @end="dragEnd"
            @add="(e: any) => onAdd(col.key, e)"
          >
            <el-card
              v-for="card in columnLists[col.key].value"
              :key="card.id"
              shadow="hover"
              class="card-item"
              @click="cardClick(card)"
            >
              <div class="card-title">
                <el-icon v-if="card.read_only" class="lock-icon"><Lock /></el-icon>
                <span class="title-text">{{ card.title || "未命名卡片" }}</span>
                <el-dropdown
                  trigger="click"
                  class="card-more"
                  @command="(cmd: string) => onMoveCommand(card, cmd)"
                  @click.stop
                >
                  <el-button text :icon="MoreFilled" size="small" @click.stop />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="c in COLUMNS"
                        :key="c.key"
                        :command="c.key"
                        :disabled="c.key === card.status"
                      >移到{{ c.label }}</el-dropdown-item>
                      <el-dropdown-item command="archive" divided :disabled="card.status === 'in_progress'">归档</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
              <div v-if="card.content" class="card-desc">{{ card.content }}</div>
              <div class="card-meta">
                <el-tag
                  v-if="card.status === 'in_progress' && card.execution_status"
                  :type="executionTagType(card.execution_status)"
                  size="small"
                  effect="dark"
                >{{ EXECUTION_LABELS[card.execution_status] || card.execution_status }}</el-tag>
                <el-tag :style="typeTagStyle(card.card_type)" size="small" effect="light">
                  {{ TYPE_LABELS[card.card_type] }}
                </el-tag>
                <el-tag
                  :type="card.priority === 'high' ? 'danger' : card.priority === 'medium' ? 'warning' : 'info'"
                  size="small"
                  effect="plain"
                >{{ PRIORITY_LABELS[card.priority] }}优先级</el-tag>
                <el-tag v-if="card.due_date" size="small" type="info" effect="plain">
                  {{ dueInDays(card.due_date) }}
                </el-tag>
                <span v-if="card.comment_count > 0" class="comment-count">
                  <el-icon><ChatDotRound /></el-icon>{{ card.comment_count }}
                </span>
              </div>
              <div v-if="card.custom_tags.length" class="card-tags">
                <el-tag v-for="t in card.custom_tags" :key="t" size="small" type="info">
                  {{ t }}
                </el-tag>
              </div>
            </el-card>
          </VueDraggable>
          <el-empty
            v-if="columnLists[col.key].value.length === 0"
            :image-size="50"
            description="暂无卡片"
          />
        </div>
        <el-button class="column-add" :icon="Plus" @click="openCreate(col.key)">新建卡片</el-button>
      </div>
    </div>

    <CardFormDialog
      v-model="dialogVisible"
      :project-id="projectId"
      :card="editingCard"
      :default-status="createStatus"
    />

    <el-drawer v-model="archiveVisible" title="归档区" size="380px">
      <el-empty v-if="archivedCards.length === 0" description="暂无归档卡片" :image-size="60" />
      <div v-else class="arch-list">
        <el-card v-for="c in archivedCards" :key="c.id" shadow="never" class="arch-item">
          <div class="arch-title">{{ c.title || "未命名卡片" }}</div>
          <div class="arch-meta">原列：{{ colLabel(c.archived_from) }}</div>
          <el-button size="small" type="primary" text @click="onRestore(c)">恢复</el-button>
        </el-card>
      </div>
    </el-drawer>

    <el-dialog v-model="autoClaimVisible" title="项目设置" width="460px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="默认模型">
          <el-select v-model="projectModel" placeholder="跟随全局默认" clearable style="width: 100%">
            <el-option v-for="o in modelOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <div class="auto-tip">该项目的 AI 默认使用此模型；留空则跟随全局默认，会话内可再切换</div>
        </el-form-item>
        <el-divider />
        <el-form-item label="自动领取">
          <el-switch v-model="autoClaim.enabled" />
          <span class="auto-tip">开启后，AI 会在设置的时间段内自动从「待办」领取任务</span>
        </el-form-item>
        <template v-if="autoClaim.enabled">
          <el-form-item label="开始时间">
            <el-time-select v-model="autoClaim.start_time" start="00:00" step="00:30" end="23:30" placeholder="开始" />
          </el-form-item>
          <el-form-item label="结束时间">
            <el-time-select v-model="autoClaim.end_time" start="00:00" step="00:30" end="23:30" placeholder="结束" />
          </el-form-item>
          <el-form-item label=" ">
            <div class="auto-cross">支持跨天（如 22:00 → 08:00），此时 AI 在夜间自动领取</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="autoClaimVisible = false">取消</el-button>
        <el-button type="primary" @click="saveProjectSettings">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.board {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.project-title {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 2px 8px 2px 0;
  border-radius: 8px;
  transition: background 0.15s;
}
.project-title:hover {
  background: #f2f3f5;
}
.project-name-text {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
}
.title-caret {
  color: #c0c4cc;
  font-size: 13px;
  transition: transform 0.15s;
}
.project-title:hover .title-caret {
  color: #909399;
}
.current {
  font-weight: 700;
  color: #409eff;
}
.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.auto-claim-btn {
  color: #8a5a00;
  background: #fef3e0;
  border-color: #d48806;
}
.auto-claim-btn:hover,
.auto-claim-btn.on {
  color: #8a5a00;
  background: #fdebd0;
  border-color: #d48806;
}
.auto-tip {
  font-size: 12px;
  color: #909399;
  margin-left: 10px;
}
.auto-cross {
  font-size: 12px;
  color: #c0c4cc;
  line-height: 1.5;
}
.search-input :deep(.el-input__wrapper) {
  background: #fff;
  box-shadow: 0 0 0 1px #e4e7ed inset;
  border-radius: 10px;
  transition: box-shadow 0.2s;
}
.search-input :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #c0c4cc inset;
}
.search-input :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  box-shadow: 0 0 0 1px #409eff inset;
}
.search-input :deep(.el-input__inner) {
  color: #303133;
}
.search-input :deep(.el-input__inner::placeholder) {
  color: #a8abb2;
}
.board-loading {
  min-height: 300px;
}
.board-columns {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: center;
}
.column {
  flex: 1 1 0;
  min-width: 0;
  max-width: 360px;
  background: #f5f7fa;
  border-radius: 10px;
  padding: 10px;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.column-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;
}
.column-stripe {
  width: 14px;
  height: 4px;
  border-radius: 2px;
  flex-shrink: 0;
}
.column-label {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}
.column-count {
  font-size: 12px;
  color: #909399;
  background: #e4e7ed;
  border-radius: 10px;
  padding: 0 8px;
  line-height: 18px;
}
.column-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 60px;
}
.column-draggable {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 40px;
}
.column-add {
  width: 100%;
  border: none;
  background: #fff;
  color: #606266;
}
.column-add:hover {
  background: #fff;
  color: #409eff;
}
.card-item {
  cursor: grab;
  border-radius: 10px;
}
.card-item:active {
  cursor: grabbing;
}
.card-ghost {
  opacity: 0.4;
  border: 1px dashed #409eff;
}
.card-ghost :deep(.el-card__body) {
  padding: 0;
}
.card-item :deep(.el-card__body) {
  padding: 12px 14px;
}
.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}
.card-more {
  margin-left: auto;
  flex-shrink: 0;
}
.title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-desc {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  word-break: break-word;
  /* 内容截断：最多 3 行，超出省略（完整内容进卡片详情查看） */
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}
.lock-icon {
  color: #909399;
  flex-shrink: 0;
}
.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.comment-count {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: #909399;
  margin-left: auto;
}
.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.form-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;
}
.arch-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.arch-item {
  border-radius: 10px;
}
.arch-title {
  font-weight: 600;
  color: #303133;
  word-break: break-word;
}
.arch-meta {
  font-size: 12px;
  color: #909399;
  margin: 4px 0 8px;
}

/* 移动端：单列 + 左右滚动切换列 */
@media (max-width: 768px) {
  .board-columns {
    overflow-x: auto;
    justify-content: flex-start;
    gap: 12px;
    padding-bottom: 10px;
    -webkit-overflow-scrolling: touch;
  }
  .column {
    flex: 0 0 80vw;
    max-width: 80vw;
  }
  .board-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .head-actions {
    width: 100%;
  }
  .head-actions .el-input {
    flex: 1;
  }
}
</style>
