<script setup lang="ts">
import { Delete, EditPen, Plus } from "@element-plus/icons-vue";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { addLLMProvider, deleteLLMProvider, getLLMSettings, getToolLLM, putToolLLM, saveLLMSettings, updateLLMProvider, type LLMProvider, type LLMModelItem, type ToolLLMSettings } from "../api/settings";

const router = useRouter();

const providers = ref<LLMProvider[]>([]);
const defaultModel = ref<{ provider_id: string; model: string } | null>(null);
const loading = ref(false);

const toolLLM = ref<ToolLLMSettings>({ name: "", base_url: "", api_key: "", model: "", enable_thinking: null });
const savingTool = ref(false);

const dialogVisible = ref(false);
const editingId = ref<string | null>(null);
const form = ref({ name: "", base_url: "", api_key: "", models: [] as LLMModelItem[] });

function maskKey(key: string): string {
  if (!key) return "（未设置）";
  if (key.length <= 8) return "••••••••";
  return `${key.slice(0, 4)}••••${key.slice(-4)}`;
}

function modelLabel(m: LLMModelItem): string {
  return m.display === m.request ? m.display : `${m.display}（${m.request}）`;
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    const data = await getLLMSettings();
    providers.value = data.providers;
    defaultModel.value = data.default;
    try {
      toolLLM.value = await getToolLLM();
    } catch {
      /* 默认空配置 */
    }
  } finally {
    loading.value = false;
  }
}

async function saveToolLLM(): Promise<void> {
  savingTool.value = true;
  try {
    toolLLM.value = await putToolLLM(toolLLM.value);
    ElMessage.success("工具模型已保存");
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    savingTool.value = false;
  }
}

onMounted(load);

async function setDefault(p: LLMProvider, m: LLMModelItem): Promise<void> {
  defaultModel.value = { provider_id: p.id, model: m.request };
  await saveLLMSettings({ providers: providers.value, default: defaultModel.value });
  ElMessage.success(`默认模型已设为 ${p.name} / ${modelLabel(m)}`);
}

function isDefault(p: LLMProvider): boolean {
  return defaultModel.value?.provider_id === p.id;
}

async function removeProvider(p: LLMProvider): Promise<void> {
  await ElMessageBox.confirm(`删除模型「${p.name}」？API Key 将一并移除。`, "确认删除", { type: "warning" });
  providers.value = (await deleteLLMProvider(p.id)).providers;
  const data = await getLLMSettings();
  defaultModel.value = data.default;
  ElMessage.success("已删除");
}

function openAdd(): void {
  editingId.value = null;
  form.value = { name: "", base_url: "", api_key: "", models: [] };
  dialogVisible.value = true;
}

function openEdit(p: LLMProvider): void {
  editingId.value = p.id;
  form.value = {
    name: p.name,
    base_url: p.base_url,
    api_key: p.api_key,
    models: p.models.map((m) => ({ display: m.display, request: m.request })),
  };
  dialogVisible.value = true;
}

async function submitAdd(): Promise<void> {
  const models = form.value.models
    .map((m) => ({ display: m.display.trim(), request: m.request.trim() }))
    .filter((m) => m.display && m.request);
  const data = editingId.value
    ? await updateLLMProvider(editingId.value, {
        name: form.value.name,
        base_url: form.value.base_url,
        api_key: form.value.api_key,
        models,
      })
    : await addLLMProvider({
        name: form.value.name,
        base_url: form.value.base_url,
        api_key: form.value.api_key,
        models,
      });
  providers.value = data.providers;
  dialogVisible.value = false;
  ElMessage.success(editingId.value ? "已保存" : "已添加");
}

function addModelRow(): void {
  form.value.models.push({ display: "", request: "" });
}
</script>

<template>
  <div class="llm-settings">
    <el-page-header content="大模型设置" @back="router.push('/settings')" />

    <el-card shadow="never" class="card">
      <template #header>
        <div class="head">
          <span class="card-title">模型列表</span>
          <el-button type="primary" :icon="Plus" @click="openAdd()">添加模型</el-button>
        </div>
      </template>

      <div v-loading="loading" class="provider-list">
        <el-empty v-if="!loading && providers.length === 0" description="还没有配置模型，点击右上角添加" :image-size="60" />
        <div v-for="p in providers" :key="p.id" class="provider-item">
          <div class="provider-info">
            <div class="provider-name">
              {{ p.name }}
              <el-tag v-if="defaultModel?.provider_id === p.id" size="small" type="success" effect="plain">默认</el-tag>
            </div>
            <div class="provider-url">{{ p.base_url }}</div>
            <div class="provider-meta">
              <span>API Key：{{ maskKey(p.api_key) }}</span>
              <span>模型：{{ p.models.length ? p.models.map(modelLabel).join(" / ") : "（未填）" }}</span>
            </div>
          </div>
          <div class="provider-actions">
            <el-dropdown v-if="p.models.length > 1" trigger="click" @command="(m: LLMModelItem) => setDefault(p, m)">
              <el-button
                text
                :type="isDefault(p) ? 'success' : 'primary'"
              >{{ isDefault(p) ? "默认" : "设为默认" }}</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="m in p.models"
                    :key="m.request"
                    :command="m"
                  >{{ modelLabel(m) }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-else-if="p.models.length === 1"
              text
              :type="isDefault(p) ? 'success' : 'primary'"
              @click="setDefault(p, p.models[0])"
            >{{ isDefault(p) ? "默认" : "设为默认" }}</el-button>
            <el-button :icon="EditPen" circle plain title="编辑" @click="openEdit(p)" />
            <el-button :icon="Delete" circle plain title="删除" @click="removeProvider(p)" />
          </div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="card">
      <template #header>
        <div class="head">
          <span class="card-title">工具模型</span>
          <span class="card-sub">标题提炼等轻任务专用，留空则使用全局默认模型</span>
        </div>
      </template>
      <el-form label-width="110px" label-position="left" class="tool-form">
        <el-form-item label="名称">
          <el-input v-model="toolLLM.name" placeholder="如：硅基流动（工具）" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="toolLLM.base_url" placeholder="https://api.siliconflow.cn/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="toolLLM.api_key" type="password" show-password placeholder="独立于大模型的 API Key" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="toolLLM.model" placeholder="如：Qwen/Qwen3.5-4B" />
        </el-form-item>
        <el-form-item label="关闭思考">
          <el-switch v-model="toolLLM.enable_thinking" :active-value="false" :inactive-value="true" />
          <div class="auto-tip">开 = 关闭 thinking（更快，适合标题提炼）；仅部分平台支持（如硅基流动）</div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingTool" @click="saveToolLLM()">保存工具模型</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模型' : '添加模型'" width="480px">
      <el-form label-width="100px" label-position="left">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：DeepSeek / 自定义" />
        </el-form-item>
        <el-form-item label="Base URL" required>
          <el-input v-model="form.base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password placeholder="留空则不设置" />
        </el-form-item>
        <el-form-item label="模型列表">
          <div class="models-table">
            <div class="models-row models-head">
              <span>显示名称</span>
              <span>实际请求模型</span>
              <span class="row-op"></span>
            </div>
            <div v-for="(m, i) in form.models" :key="i" class="models-row">
              <el-input v-model="m.display" placeholder="如：快版" />
              <el-input v-model="m.request" placeholder="如：glm-5.3-flash" />
              <el-button
                class="row-op"
                :icon="Delete"
                circle
                text
                title="删除该模型"
                @click="form.models.splice(i, 1)"
              />
            </div>
            <el-button text type="primary" :icon="Plus" @click="addModelRow()">添加模型行</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!form.name || !form.base_url" @click="submitAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.llm-settings {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.card {
  border-radius: 10px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title {
  font-weight: 600;
}
.provider-list {
  min-height: 100px;
}
.provider-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid #f0f2f5;
}
.provider-item:last-child {
  border-bottom: none;
}
.provider-name {
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.provider-url {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.provider-meta {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
  display: flex;
  gap: 16px;
}
.provider-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.models-table {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.models-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.models-row > .el-input {
  flex: 1;
}
.models-head {
  font-size: 12px;
  color: #909399;
}
.row-op {
  width: 32px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.card-sub { font-size: 12px; color: #909399; }
.tool-form { max-width: 480px; }
</style>
