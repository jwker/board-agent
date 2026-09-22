<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, ArrowLeft, ArrowRight, EditPen, Expand, Fold, VideoPause, VideoPlay } from "@element-plus/icons-vue";

import { approveCard, executeCard, getCard, stopCard, updateCard, type Card } from "@/api/cards";
import { EXECUTION_LABELS, TYPE_LABELS, executionTagType, typeTagStyle } from "@/constants/card";
import { getProject, type Project } from "@/api/projects";
import { onWS } from "@/api/ws";
import { createComment, listComments, type Comment, type StepItem } from "@/api/comments";
import { getLLMSettings, type LLMSettings } from "@/api/settings";
import { useCardsStore } from "@/stores/cards";
import CardFormDialog from "@/components/CardFormDialog.vue";
import GlobalActions from "@/components/GlobalActions.vue";
import { renderMarkdown, renderStreamingMarkdown } from "@/utils/markdown";

const props = defineProps<{ projectId: string; cardId: string }>();
const router = useRouter();
const cardsStore = useCardsStore();

const project = ref<Project | null>(null);
const card = ref<Card | null>(null);
const comments = ref<Comment[]>([]);
const newComment = ref("");
const sending = ref(false);
const editVisible = ref(false);
const executing = ref(false);

/** 手动触发 AI 执行：后端仅进行中卡片允许；状态经 WS card.updated 就地更新 */
async function runExecute() {
  executing.value = true;
  try {
    await executeCard(card.value!.id, sessionModel.value || undefined);
    ElMessage.success("已触发 AI 执行");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail ?? "触发失败");
  } finally {
    executing.value = false;
  }
}

/** 停止进行中的 AI 执行 */
const stopping = ref(false);
async function runStop() {
  if (!card.value) return;
  stopping.value = true;
  try {
    await stopCard(card.value.id);
    ElMessage.success("已停止执行");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail ?? "停止失败");
  } finally {
    stopping.value = false;
  }
}

/** 3.4 审批面板：批准 / 拒绝（原因）/ 编辑命令后执行 */
const approving = ref(false);
const editingIndex = ref<number | null>(null);
const editCommand = ref("");

function startEdit() {
  const cmd = card.value?.execution_payload?.actions?.[0]?.args?.command;
  editCommand.value = typeof cmd === "string" ? cmd : "";
  editingIndex.value = 0;
}

async function submitApproval(decision: "approve" | "reject" | "edit", rejectMessage = "") {
  if (!card.value) return;
  approving.value = true;
  try {
    const body: { decision: "approve" | "reject" | "edit"; message?: string; command?: string } = { decision };
    if (decision === "reject") body.message = rejectMessage.trim();
    if (decision === "edit") body.command = editCommand.value.trim();
    await approveCard(card.value.id, body);
    ElMessage.success(decision === "approve" ? "已批准，AI 继续执行" : decision === "reject" ? "已拒绝，AI 将调整方案" : "已按新命令继续执行");
    editingIndex.value = null;
    editCommand.value = "";
    // 状态经 WS 推送更新；双保险拉一次
    card.value = await getCard(card.value.id);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail ?? "审批提交失败");
  } finally {
    approving.value = false;
  }
}

async function rejectDialog() {
  try {
    const { value } = await ElMessageBox.prompt("拒绝原因（可选）", "拒绝执行", {
      confirmButtonText: "拒绝",
      cancelButtonText: "取消",
      inputPlaceholder: "例如：不要动这个文件",
      inputValidator: () => true,
    });
    await submitApproval("reject", value ?? "");
  } catch {
    /* 用户取消 */
  }
}
const llmSettings = ref<LLMSettings>({ providers: [], default: null });
const sessionModel = ref("");

const modelOptions = computed(() => {
  const opts: { value: string; label: string }[] = [];
  for (const p of llmSettings.value.providers) {
    for (const m of p.models) {
      const label = m.display === m.request ? m.display : `${m.display}（${m.request}）`;
      opts.push({ value: `${p.id}::${m.request}`, label: `${p.name} / ${label}` });
    }
  }
  return opts;
});

const STATUS_LABELS: Record<string, string> = {
  backlog: "积压",
  todo: "待办",
  in_progress: "进行中",
  done: "已完成",
  archived: "已归档",
};

const STATUS_TAG_TYPES: Record<string, "info" | "primary" | "warning" | "success"> = {
  backlog: "info",
  todo: "primary",
  in_progress: "warning",
  done: "success",
  archived: "info",
};

onMounted(async () => {
  try {
    card.value = await getCard(Number(props.cardId));
    project.value = await getProject(Number(props.projectId));
    comments.value = await listComments(card.value.id);
    scrollIssueToBottom();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载失败");
  }
  try {
    llmSettings.value = await getLLMSettings();
    // 会话级模型：进入页面默认跟随全局配置；切换仅本次页面临时生效，刷新/退出即恢复
    if (llmSettings.value.default?.provider_id) {
      sessionModel.value = `${llmSettings.value.default.provider_id}::${llmSettings.value.default.model}`;
    }
  } catch {
    /* 未配置模型时下拉为空 */
  }
  window.addEventListener("ws-reconnected", reloadData);
  const issueEl = document.querySelector(".issue") as HTMLElement | null;
  issueEl?.addEventListener("scroll", onIssueScroll, { passive: true });
});

async function reloadData(): Promise<void> {
  // WS 重连后全量重拉当前视图（TECH-DESIGN §4 断线补偿）
  try {
    card.value = await getCard(Number(props.cardId));
    comments.value = await listComments(card.value.id);
    scrollIssueToBottom();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "刷新失败");
  }
}

const offCardUpdated = onWS("card.updated", (msg) => {
  const { card_id, title, execution_status } = msg.payload as {
    card_id?: number;
    title?: string;
    execution_status?: string;
  };
  if (card_id === Number(props.cardId) && card.value) {
    const patch: Record<string, string> = {};
    if (typeof title === "string") patch.title = title;
    if (typeof execution_status === "string") patch.execution_status = execution_status;
    if (Object.keys(patch).length) card.value = { ...card.value, ...patch };
    if (execution_status === "waiting_approval") {
      // WS 不带审批载荷：挂起时重拉卡片，让审批面板拿到 execution_payload
      // 流式区保留已输出部分（静态展示），不再追加
      streamingActive.value = false;
      streamingWaiting.value = true;
      getCard(Number(props.cardId))
        .then((c) => {
          if (card.value) card.value = c;
        })
        .catch(() => {});
    } else if (execution_status === "running") {
      // 新一轮执行（含审批恢复后）：重置文本流式区，开始增量展示；
      // 步骤保留（跨审批累积，恢复后新步骤继续追加）
      streamingActive.value = true;
      streamingWaiting.value = false;
      streamingText.value = "";
    } else if (
      execution_status === "completed" ||
      execution_status === "failed" ||
      execution_status === "cancelled"
    ) {
      // 执行终态：清理流式区；正式评论（含 steps）经 comment.created 重拉展示
      streamingActive.value = false;
      streamingWaiting.value = false;
      streamingText.value = "";
      streamingSteps.value = [];
    }
  }
});

// AI 回复流式增量：逐块追加到评论区"AI 正在输入"占位
const streamingText = ref("");
const streamingActive = ref(false);
const streamingWaiting = ref(false);
const offCardStream = onWS("card.stream", (msg) => {
  const { card_id, delta } = msg.payload as { card_id?: number; delta?: string };
  if (card_id === Number(props.cardId) && typeof delta === "string" && delta) {
    streamingActive.value = true;
    streamingWaiting.value = false;
    streamingText.value += delta;
    if (!followPaused && issueNearBottom()) scrollIssueToBottom();
  }
});

// 工具调用步骤（执行中实时追加；完成/失败/停止后由正式评论的 steps 承接）
const streamingSteps = ref<StepItem[]>([]);
const streamingStepsOpen = ref(false); // 流式步骤折叠
const offCardStep = onWS("card.step", (msg) => {
  const { card_id, step } = msg.payload as { card_id?: number; step?: StepItem };
  if (card_id === Number(props.cardId) && step && typeof step.index === "number") {
    streamingActive.value = true;
    const arr = [...streamingSteps.value];
    if (arr[step.index]) arr[step.index] = { ...arr[step.index], ...step };
    else arr[step.index] = step;
    streamingSteps.value = arr;
    if (!followPaused && issueNearBottom()) scrollIssueToBottom();
  }
});

// 正式评论内 steps 的展开状态：commentId -> 折叠面板开关；`cid-idx` -> 结果全文开关
const commentStepsOpen = ref<Record<number, boolean>>({});
const stepFullOpen = ref<Record<string, boolean>>({});

function toggleCommentSteps(commentId: number) {
  commentStepsOpen.value = { ...commentStepsOpen.value, [commentId]: !commentStepsOpen.value[commentId] };
}
function toggleStepFull(key: string) {
  stepFullOpen.value = { ...stepFullOpen.value, [key]: !stepFullOpen.value[key] };
}

/** 参数 JSON 美化 + 截断（过长展示前 200 字） */
function formatStepArgs(args: unknown): string {
  if (args === undefined || args === null) return "";
  let s: string;
  if (typeof args === "string") s = args;
  else {
    try {
      s = JSON.stringify(args);
    } catch {
      s = String(args);
    }
  }
  return s.length > 200 ? s.slice(0, 200) + "…" : s;
}

// AI 回帖（执行完成等）实时插入评论区：事件只带 card_id/comment_id，重拉列表最可靠
const offCommentCreated = onWS("comment.created", (msg) => {
  const { card_id } = msg.payload as { card_id?: number };
  if (card_id === Number(props.cardId)) {
    reloadComments().catch(() => {});
  }
});

onBeforeUnmount(() => {
  const issueEl = document.querySelector(".issue") as HTMLElement | null;
  issueEl?.removeEventListener("scroll", onIssueScroll);
  window.removeEventListener("ws-reconnected", reloadData);
  offCardUpdated();
  offCardStream();
  offCommentCreated();
});

function changeSessionModel(v: string) {
  sessionModel.value = v;
  const label = modelOptions.value.find((o) => o.value === v)?.label ?? v;
  ElMessage.success(`本次会话使用：${label}（刷新后恢复默认）`);
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

async function toggleReadOnly() {
  if (!card.value) return;
  try {
    card.value = await updateCard(card.value.id, { read_only: !card.value.read_only });
    ElMessage.success(card.value.read_only ? "已开启只读：AI 后续操作仅只读，不写文件" : "已关闭只读：AI 可正常读写");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "切换失败");
  }
}

// 评论滚动：容器内列表（.issue）。进入/新评论直接滚到底；流式输出时自动跟随。
// 用户手动滚动（上翻/拖拽等）后暂停跟随，直到滚回底部自动恢复，方便一边输出一边手动查看。
let followPaused = false;
let programScroll = false;

function issueNearBottom(): boolean {
  const el = document.querySelector(".issue") as HTMLElement | null;
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
}

function scrollIssueToBottom(): void {
  programScroll = true;
  nextTick(() => {
    const el = document.querySelector(".issue") as HTMLElement | null;
    if (el) el.scrollTop = el.scrollHeight;
    requestAnimationFrame(() => {
      programScroll = false;
    });
  });
}

function onIssueScroll(): void {
  if (programScroll) return; // 程序滚动（自动跟随/初始化）不视为用户干预
  followPaused = !issueNearBottom(); // 用户滚离底部 → 暂停跟随；滚回底部 → 恢复
}

async function reloadComments() {
  if (!card.value) return;
  comments.value = await listComments(card.value.id);
  scrollIssueToBottom();
}

async function sendComment() {
  const content = newComment.value.trim();
  if (!content || !card.value) return;
  sending.value = true;
  try {
    const created = await createComment(card.value.id, content, sessionModel.value || undefined);
    comments.value.push(created);
    newComment.value = "";
    scrollIssueToBottom();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "评论失败");
  } finally {
    sending.value = false;
  }
}

function onSaved(saved: Card) {
  card.value = saved;
  cardsStore.replaceCard(saved);
}

function goBack() {
  // 优先浏览器历史后退（回到来源页），无历史时兜底回看板
  if (window.history.length > 1) {
    router.back();
  } else {
    router.push(`/projects/${props.projectId}/board`);
  }
}

const sideOpen = ref(false);

function shortThreadId(threadId: string | null): string {
  // thread_id 形如 card-12：解析出真实卡片号，避免截断成 card-1
  if (!threadId) return "?";
  const m = threadId.match(/^card-(\d+)$/);
  return m ? m[1] : threadId;
}
</script>

<template>
  <div class="detail">
    <div class="detail-head">
      <el-button text :icon="ArrowLeft" @click="goBack">返回看板</el-button>
      <div v-if="card" class="head-tools">
        <span class="cfg-label">只读</span>
        <el-switch :model-value="card.read_only" @change="toggleReadOnly" />
        <el-tag v-if="card.read_only" size="small" type="primary" effect="plain">AI 不写文件、仅只读命令</el-tag>
        <span class="cfg-label">模型</span>
        <el-select
          v-model="sessionModel"
          placeholder="选择会话模型"
          class="model-select"
          :disabled="modelOptions.length === 0"
          @change="changeSessionModel"
        >
          <el-option v-for="o in modelOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <el-tooltip :content="sideOpen ? '收起侧边栏' : '展开侧边栏'">
          <el-button
            class="side-toggle-btn"
            :icon="sideOpen ? Fold : Expand"
            circle
            @click="sideOpen = !sideOpen"
          />
        </el-tooltip>
        <GlobalActions class="detail-global" />
      </div>
    </div>

    <template v-if="card">
      <div class="detail-grid" :class="{ 'no-side': !sideOpen }">
        <div class="detail-left">
          <el-card shadow="never" class="card-panel">
        <div class="card-head">
          <div class="head-main">
            <div class="title-row">
              <span class="thread-badge">对话 #{{ props.cardId }}</span>
              <h1 class="title">{{ card.title || "未命名卡片" }}</h1>
              <div class="title-actions">
                <el-button
                  v-if="card.status === 'in_progress' && card.execution_status !== 'running'"
                  size="small"
                  :loading="executing"
                  :icon="VideoPlay"
                  @click="runExecute"
                >立即执行</el-button>
                <el-button
                  v-if="card.status === 'in_progress' && card.execution_status === 'running'"
                  size="small"
                  type="danger"
                  plain
                  :loading="stopping"
                  :icon="VideoPause"
                  @click="runStop"
                >停止</el-button>
                <el-button size="small" :icon="EditPen" @click="editVisible = true">编辑</el-button>
              </div>
            </div>
            <div class="sub">
              创建于 {{ formatTime(card.created_at) }} · 项目：{{ project?.name ?? "-" }} · 当前列：{{ STATUS_LABELS[card.status] }}
            </div>
            <div class="custom-tags">
              <el-tag :style="typeTagStyle(card.card_type)" size="small" effect="light">
                {{ TYPE_LABELS[card.card_type] }}
              </el-tag>
              <el-tag v-for="t in card.custom_tags" :key="t" size="small" type="info" effect="light">
                {{ t }}
              </el-tag>
            </div>
            <el-tag
              v-if="card.execution_status"
              class="exec-tag"
              :type="executionTagType(card.execution_status)"
              size="small"
              effect="dark"
            >{{ EXECUTION_LABELS[card.execution_status] || card.execution_status }}</el-tag>
            <div
              v-if="card.execution_status === 'waiting_approval' && card.execution_payload"
              class="approval-panel"
            >
              <div class="ap-title">AI 请求执行以下命令，等待审批</div>
              <div v-for="(a, i) in card.execution_payload.actions" :key="i" class="ap-cmd">
                <code v-if="editingIndex !== i">{{ (a.args.command as string) ?? "" }}</code>
                <el-input
                  v-else
                  v-model="editCommand"
                  size="small"
                  placeholder="输入替代命令"
                />
              </div>
              <div class="ap-actions">
                <el-button size="small" type="success" :loading="approving" @click="submitApproval('approve')">
                  批准执行
                </el-button>
                <el-button size="small" type="danger" :loading="approving" @click="rejectDialog">
                  拒绝
                </el-button>
                <template v-if="editingIndex === null">
                  <el-button size="small" @click="startEdit">编辑命令</el-button>
                </template>
                <template v-else>
                  <el-button size="small" type="primary" :loading="approving" @click="submitApproval('edit')">
                    执行新命令
                  </el-button>
                  <el-button size="small" @click="editingIndex = null; editCommand = ''">取消</el-button>
                </template>
              </div>
            </div>
            <div v-if="card.content" class="card-content md-body" v-html="renderMarkdown(card.content)"></div>
          </div>
        </div>
          </el-card>

          <el-card shadow="never" class="panel">
          <template #header>
            <div class="panel-h">讨论（Issue 式回帖）</div>
          </template>
          <div class="issue">
            <div v-for="c in comments" :key="c.id" class="item">
              <div :class="['avatar', c.author === 'ai' ? 'ai' : 'me']">
                {{ c.author === "ai" ? "AI" : "我" }}
              </div>
              <div class="i-body">
                <div class="i-head">
                  <span class="name">{{ c.author === "ai" ? "AI" : "我" }}</span>
                  <el-tag v-if="c.author === 'ai'" size="small" type="warning" effect="plain">
                    AI · 对话 #{{ shortThreadId(c.thread_id) }}
                  </el-tag>
                  <span class="meta">{{ formatTime(c.created_at) }}</span>
                </div>
                <div v-if="c.author === 'ai' && c.steps && c.steps.length" class="steps-block">
                  <div class="steps-head" @click="toggleCommentSteps(c.id)">
                    <span class="steps-title">调用过程（{{ c.steps.length }} 步）</span>
                    <el-icon class="steps-caret"><ArrowDown v-if="commentStepsOpen[c.id]" /><ArrowRight v-else /></el-icon>
                  </div>
                  <div v-show="commentStepsOpen[c.id]" class="steps-list">
                    <div v-for="(s, si) in c.steps" :key="si" class="step-item">
                      <div class="step-line">
                        <span class="step-name">{{ s.name || "工具" }}</span>
                        <span v-if="formatStepArgs(s.args)" class="step-args">{{ formatStepArgs(s.args) }}</span>
                        <el-tag size="small" :type="s.status === 'done' ? 'success' : 'warning'" effect="plain">
                          {{ s.status === "done" ? "完成" : "执行中" }}
                        </el-tag>
                      </div>
                      <div v-if="s.result" class="step-result">
                        <template v-if="stepFullOpen[`${c.id}-${si}`] && s.result_full">
                          <pre class="step-full">{{ s.result_full }}</pre>
                        </template>
                        <template v-else>{{ s.result }}</template>
                        <span
                          v-if="s.result_full && s.result_full.length > (s.result || '').length"
                          class="step-full-toggle"
                          @click.stop="toggleStepFull(`${c.id}-${si}`)"
                        >
                          {{ stepFullOpen[`${c.id}-${si}`] ? "收起" : "查看完整" }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="i-content md-body" v-html="renderMarkdown(c.content)"></div>
              </div>
            </div>

            <div
              v-if="streamingActive || streamingText"
              class="item streaming-item"
              :class="{ 'streaming-active': streamingActive }"
            >
              <div class="avatar ai">AI</div>
              <div class="i-body">
                <div class="i-head">
                  <span class="name">AI</span>
                  <el-tag v-if="streamingWaiting" size="small" type="info" effect="plain">
                    等待人工审批 · 已输出部分
                  </el-tag>
                  <span class="meta" v-else>正在输出…</span>
                </div>
                <div v-if="streamingSteps.length" class="steps-block">
                  <div class="steps-head" @click="streamingStepsOpen = !streamingStepsOpen">
                    <span class="steps-title">调用过程（{{ streamingSteps.length }} 步）</span>
                    <el-icon class="steps-caret"><ArrowDown v-if="streamingStepsOpen" /><ArrowRight v-else /></el-icon>
                  </div>
                  <div v-show="streamingStepsOpen" class="steps-list">
                    <div v-for="s in streamingSteps" :key="s.index" class="step-item">
                      <div class="step-line">
                        <span class="step-name">{{ s.name || "工具" }}</span>
                        <span v-if="formatStepArgs(s.args)" class="step-args">{{ formatStepArgs(s.args) }}</span>
                        <el-tag size="small" :type="s.status === 'done' ? 'success' : 'warning'" effect="plain">
                          {{ s.status === "done" ? "完成" : "执行中" }}
                        </el-tag>
                      </div>
                      <div v-if="s.result" class="step-result">
                        <template v-if="stepFullOpen[`s-${s.index}`] && s.result_full">
                          <pre class="step-full">{{ s.result_full }}</pre>
                        </template>
                        <template v-else>{{ s.result }}</template>
                        <span
                          v-if="s.result_full && s.result_full.length > (s.result || '').length"
                          class="step-full-toggle"
                          @click.stop="toggleStepFull(`s-${s.index}`)"
                        >
                          {{ stepFullOpen[`s-${s.index}`] ? "收起" : "查看完整" }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="i-content md-body streaming-body" v-html="renderStreamingMarkdown(streamingText)"></div>
              </div>
            </div>

            <el-empty
              v-if="comments.length === 0 && !streamingActive && !streamingText"
              :image-size="60"
              description="还没有评论，留下第一条吧"
            />
          </div>
          <div class="composer">
            <el-input
              v-model="newComment"
              type="textarea"
              :rows="2"
              resize="none"
              placeholder="写下评论…（评论即对话，非进行中仅记录，不触发 AI）"
            />
            <el-button
              type="primary"
              :loading="sending"
              :disabled="!newComment.trim()"
              @click="sendComment"
            >评论</el-button>
          </div>
        </el-card>
        </div>

        <div v-if="sideOpen" class="side">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-h">产物</div>
            </template>
            <el-empty :image-size="60" description="暂无产物（AI 生成）" />
          </el-card>
        </div>
      </div>
    </template>

    <el-skeleton v-else :rows="6" animated />

    <CardFormDialog
      v-model="editVisible"
      :project-id="Number(projectId)"
      :card="card"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.head-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.cfg-label {
  font-size: 13px;
  color: #606266;
}
.model-select {
  width: 280px;
}
@media (max-width: 768px) {
  .model-select {
    width: 100%;
    max-width: 280px;
  }
}
.card-panel {
  border-radius: 10px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.head-main {
  min-width: 0;
  flex: 1;
}
.title {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
  margin: 0;
}
.card-content {
  margin-top: 10px;
  color: #303133;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}
.sub {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.title-row .title {
  flex: 1;
  min-width: 0;
}
.thread-badge {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: #909399;
  background: #f4f4f5;
  border-radius: 6px;
  padding: 3px 9px;
  line-height: 1.4;
}
.title-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.custom-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
/* 执行状态标签统一与上方标签区拉开上边距 */
.approval-panel {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--el-color-warning-light-7);
  border-radius: 8px;
  background: var(--el-color-warning-light-9);
}
.ap-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-warning-dark-2);
  margin-bottom: 8px;
}
.ap-cmd {
  margin-bottom: 6px;
}
.ap-cmd code {
  display: block;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
  word-break: break-all;
  white-space: pre-wrap;
}
.ap-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.exec-tag {
  margin-top: 8px;
}
/* Element Plus 相邻按钮默认 margin-left: 12px，去掉多余左侧边距 */
.title-actions .el-button + .el-button {
  margin-left: 0;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
  align-items: start;
}
.detail-grid.no-side {
  grid-template-columns: 1fr;
}
@media (max-width: 900px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .detail-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .head-tools {
    width: 100%;
  }
  .card-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .title-row {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 8px 12px;
  }
  .title-row .title {
    grid-column: 1 / -1;
    order: 2;
    font-size: 17px;
  }
  .title-row .thread-badge {
    order: 1;
    justify-self: start;
  }
  .title-row .title-actions {
    order: 1;
    justify-self: end;
  }
}
.panel {
  border-radius: 10px;
}
.panel-h {
  font-weight: 600;
  color: #303133;
}
.issue {
  display: flex;
  flex-direction: column;
  max-height: 560px;
  overflow: auto;
}
.item {
  display: flex;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 1px solid #f0f2f5;
}
.item:last-child {
  border-bottom: none;
}
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}
.avatar.me {
  background: #409eff;
}
.avatar.ai {
  background: #7b3fe4;
}
.i-body {
  flex: 1;
  min-width: 0;
}
.i-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #909399;
}
.i-head .name {
  font-weight: 700;
  color: #1f2329;
  font-size: 13px;
}
.i-title {
  font-size: 15px;
  font-weight: 700;
  margin: 6px 0 6px;
}
.i-content {
  font-size: 14px;
  line-height: 1.65;
  color: #4e5969;
  word-break: break-word;
}
.streaming-body {
  border-left: 2px solid #c8a6f5;
  padding-left: 8px;
  min-height: 1.2em;
}
.streaming-body:empty::before {
  content: "…";
  color: #909399;
}
.streaming-item.streaming-active .streaming-body::after {
  content: "▍";
  margin-left: 2px;
  color: #7b3fe4;
  animation: streaming-blink 1s step-start infinite;
}
@keyframes streaming-blink {
  50% {
    opacity: 0;
  }
}
.composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
  padding-top: 12px;
  border-top: 1px solid #f0f2f5;
}
.composer .el-textarea {
  width: 100%;
}
.composer .el-button {
  align-self: flex-end;
}
.detail-left {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
/* PC 端讨论区撑满视口高度：el-card 列布局，评论列表 flex 撑满剩余空间，输入框贴底 */
@media (min-width: 901px) {
  .detail-left {
    height: calc(100vh - 170px);
  }
  .detail-left > .card-panel {
    flex-shrink: 0;
  }
  .detail-left > .panel {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  .detail-left > .panel :deep(.el-card__body) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .detail-left > .panel .issue {
    flex: 1;
    min-height: 0;
    max-height: none;
  }
  .detail-left > .panel .composer {
    flex-shrink: 0;
  }
}
</style>

<style>
/* Markdown 渲染样式（v-html 内容不参与 scoped，用非 scoped 块；卡片主体与评论共用） */
.md-body {
  word-break: break-word;
  line-height: 1.7;
}
.md-body > :first-child {
  margin-top: 0;
}
.md-body > :last-child {
  margin-bottom: 0;
}
.md-body p {
  margin: 6px 0;
}
.md-body h1,
.md-body h2,
.md-body h3,
.md-body h4,
.md-body h5,
.md-body h6 {
  margin: 14px 0 8px;
  font-weight: 700;
  color: #303133;
  line-height: 1.4;
}
.md-body h1 {
  font-size: 20px;
}
.md-body h2 {
  font-size: 18px;
}
.md-body h3 {
  font-size: 16px;
}
.md-body h4,
.md-body h5,
.md-body h6 {
  font-size: 15px;
}
.md-body ul,
.md-body ol {
  margin: 6px 0;
  padding-left: 22px;
}
.md-body li {
  margin: 3px 0;
}
.md-body code {
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 12.5px;
  font-family: "SF Mono", Menlo, Consolas, monospace;
  color: #c7254e;
}
.md-body pre {
  background: #f7f8fa;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 12px;
  overflow-x: auto;
  margin: 8px 0;
}
.md-body pre code {
  background: none;
  border: none;
  padding: 0;
  color: inherit;
  font-size: 13px;
}
.md-body blockquote {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid #409eff;
  color: #606266;
  background: #f8fbff;
}
.md-body table {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
}
.md-body th,
.md-body td {
  border: 1px solid #e4e7ed;
  padding: 6px 10px;
  font-size: 13px;
}
.md-body th {
  background: #f5f7fa;
  font-weight: 600;
}
.md-body a {
  color: #409eff;
  text-decoration: none;
}
.md-body a:hover {
  text-decoration: underline;
}
.md-body img {
  max-width: 100%;
  border-radius: 4px;
}
.md-body hr {
  border: none;
  border-top: 1px solid #e4e7ed;
  margin: 12px 0;
}
.md-body input[type="checkbox"] {
  margin-right: 6px;
}

/* 调用过程折叠块（正式评论 + 流式区共用） */
.steps-block {
  margin: 8px 0 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  overflow: hidden;
  background: var(--el-fill-color-lighter);
}
.steps-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
}
.steps-head:hover {
  background: var(--el-fill-color);
}
.steps-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
.steps-caret {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.steps-list {
  border-top: 1px dashed var(--el-border-color-lighter);
  padding: 6px 10px;
  max-height: 360px;
  overflow: auto;
}
.step-item {
  padding: 4px 0;
}
.step-item + .step-item {
  border-top: 1px solid var(--el-border-color-extra-light);
}
.step-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.step-name {
  font-family: var(--el-font-family-mono, monospace);
  color: var(--el-color-primary);
  font-weight: 600;
}
.step-args {
  color: var(--el-text-color-secondary);
  font-family: var(--el-font-family-mono, monospace);
  word-break: break-all;
}
.step-result {
  margin-top: 3px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}
.step-full {
  margin: 4px 0;
  padding: 6px 8px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.step-full-toggle {
  color: var(--el-color-primary);
  cursor: pointer;
  margin-left: 6px;
  font-size: 12px;
}
.step-full-toggle:hover {
  text-decoration: underline;
}

</style>
