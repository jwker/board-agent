<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowLeft, EditPen } from "@element-plus/icons-vue";

import { getCard, updateCard, type Card } from "@/api/cards";
import { TYPE_LABELS, typeTagStyle } from "@/constants/card";
import { getProject, type Project } from "@/api/projects";
import { createComment, listComments, type Comment } from "@/api/comments";
import { getLLMSettings, type LLMSettings } from "@/api/settings";
import { useCardsStore } from "@/stores/cards";
import CardFormDialog from "@/components/CardFormDialog.vue";

const props = defineProps<{ projectId: string; cardId: string }>();
const router = useRouter();
const cardsStore = useCardsStore();

const project = ref<Project | null>(null);
const card = ref<Card | null>(null);
const comments = ref<Comment[]>([]);
const newComment = ref("");
const sending = ref(false);
const editVisible = ref(false);
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
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "加载失败");
  }
  try {
    llmSettings.value = await getLLMSettings();
    // 会话级模型：优先记住上次选择，其次全局默认
    const saved = localStorage.getItem("session-model");
    if (saved && modelOptions.value.some((o) => o.value === saved)) {
      sessionModel.value = saved;
    } else if (llmSettings.value.default?.provider_id) {
      sessionModel.value = `${llmSettings.value.default.provider_id}::${llmSettings.value.default.model}`;
    }
  } catch {
    /* 未配置模型时下拉为空 */
  }
});

function changeSessionModel(v: string) {
  sessionModel.value = v;
  localStorage.setItem("session-model", v);
  const label = modelOptions.value.find((o) => o.value === v)?.label ?? v;
  ElMessage.success(`会话模型：${label}`);
}

const sessionLabel = computed(() =>
  card.value ? `会话 #${Math.abs(card.value.id * 7919).toString(16).toUpperCase().slice(0, 4)}` : "",
);

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

async function sendComment() {
  const content = newComment.value.trim();
  if (!content || !card.value) return;
  sending.value = true;
  try {
    const created = await createComment(card.value.id, content);
    comments.value.push(created);
    newComment.value = "";
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

function shortThreadId(threadId: string | null): string {
  return threadId ? threadId.slice(0, 6) : "?";
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
          style="width: 180px"
          :disabled="modelOptions.length === 0"
          @change="changeSessionModel"
        >
          <el-option v-for="o in modelOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </div>
    </div>

    <template v-if="card">
      <el-card shadow="never" class="card-panel">
        <div class="card-head">
          <div class="head-main">
            <h1 class="title">{{ card.title || "未命名卡片" }}</h1>
            <div class="sub">
              创建于 {{ formatTime(card.created_at) }} · 项目：{{ project?.name ?? "-" }} · 当前列：{{ STATUS_LABELS[card.status] }}
            </div>
            <div v-if="card.content" class="card-content">{{ card.content }}</div>
          </div>
          <el-tag :style="typeTagStyle(card.card_type)" size="small" effect="light">
            {{ TYPE_LABELS[card.card_type] }}
          </el-tag>
          <el-tag v-for="t in card.custom_tags" :key="t" size="small" type="info" effect="light">
            {{ t }}
          </el-tag>
          <div class="head-actions">
            <el-button :icon="EditPen" @click="editVisible = true">编辑</el-button>
          </div>
        </div>
      </el-card>

      <div class="detail-grid">
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
                  <span class="name">{{ c.author === "ai" ? sessionLabel : "我" }}</span>
                  <el-tag v-if="c.author === 'ai'" size="small" type="warning" effect="plain">
                    AI · 对话 #{{ shortThreadId(c.thread_id) }}
                  </el-tag>
                  <span class="meta">{{ formatTime(c.created_at) }}</span>
                </div>
                <div class="i-content">{{ c.content }}</div>
              </div>
            </div>

            <el-empty
              v-if="comments.length === 0"
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

        <div class="side">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-h">AI 执行步骤</div>
            </template>
            <el-empty :image-size="60" description="AI 尚未开始执行（阶段 3 接入）" />
          </el-card>
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-h">产物</div>
            </template>
            <el-empty :image-size="60" description="暂无产物（AI 生成，阶段 4 接入）" />
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
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}
.sub {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
.head-actions {
  display: flex;
  gap: 8px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
  align-items: start;
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
  white-space: pre-wrap;
  word-break: break-word;
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
.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
