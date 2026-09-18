<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { Lock } from "@element-plus/icons-vue";

import {
  type Card,
  type CardStatus,
  type CardType,
  type Priority,
} from "@/api/cards";
import { TYPE_LABELS } from "@/constants/card";
import { useCardsStore } from "@/stores/cards";

const props = defineProps<{
  modelValue: boolean;
  projectId: number;
  card?: Card | null; // 编辑时传入；新建为 null
  defaultStatus?: CardStatus;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "saved", card: Card): void;
}>();

const cardsStore = useCardsStore();
const formRef = ref<FormInstance>();
const saving = ref(false);

const COLUMNS: { key: CardStatus; label: string }[] = [
  { key: "backlog", label: "积压" },
  { key: "todo", label: "待办" },
  { key: "in_progress", label: "进行中" },
  { key: "done", label: "已完成" },
];

const form = reactive({
  title: "",
  content: "",
  card_type: "task" as CardType,
  custom_tags: "",
  priority: "medium" as Priority,
  status: "backlog" as CardStatus,
  acceptance_criteria: "",
  due_date: "",
  remark: "",
  read_only: false,
});

const rules: FormRules = {
  content: [{ required: true, message: "请输入内容", trigger: "blur" }],
};

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    const card = props.card;
    Object.assign(form, {
      title: card?.title ?? "",
      content: card?.content ?? "",
      card_type: card?.card_type ?? "task",
      custom_tags: (card?.custom_tags ?? []).join("、"),
      priority: card?.priority ?? "medium",
      status: card?.status ?? props.defaultStatus ?? "backlog",
      acceptance_criteria: card?.acceptance_criteria ?? "",
      due_date: card?.due_date ?? "",
      remark: card?.remark ?? "",
      read_only: card?.read_only ?? false,
    });
  },
);

async function save() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  saving.value = true;
  const body = {
    title: form.title.trim(),
    content: form.content.trim(),
    card_type: form.card_type,
    custom_tags: form.custom_tags
      .split(/[、,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean),
    priority: form.priority,
    status: form.status,
    acceptance_criteria: form.acceptance_criteria.trim() || null,
    due_date: form.due_date || null,
    remark: form.remark.trim() || null,
    read_only: form.read_only,
  };
  try {
    const saved = props.card
      ? await cardsStore.editCard(props.card.id, body)
      : await cardsStore.addCard(props.projectId, body);
    ElMessage.success(props.card ? "卡片已更新" : "卡片已创建");
    emit("saved", saved);
    emit("update:modelValue", false);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="card ? '编辑卡片' : '新建卡片'"
    width="min(560px, 94vw)"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="标题">
        <el-input v-model="form.title" maxlength="200" show-word-limit placeholder="留空：创建后由 AI 自动总结（阶段 3 接入）" />
      </el-form-item>
      <el-form-item label="描述" prop="content">
        <el-input v-model="form.content" type="textarea" :rows="3" placeholder="说明需求背景等…（必填）" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="类型">
            <el-select v-model="form.card_type" style="width: 100%">
              <el-option v-for="(label, key) in TYPE_LABELS" :key="key" :label="label" :value="key" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="优先级">
            <el-select v-model="form.priority" style="width: 100%">
              <el-option label="高" value="high" />
              <el-option label="中" value="medium" />
              <el-option label="低" value="low" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item v-if="!card" label="入列位置">
        <el-select v-model="form.status" style="width: 100%">
          <el-option v-for="col in COLUMNS" :key="col.key" :label="col.label" :value="col.key" />
        </el-select>
      </el-form-item>
      <el-form-item label="自定义标签">
        <el-input v-model="form.custom_tags" placeholder="用顿号或逗号分隔，如：登录、认证" />
      </el-form-item>
      <el-form-item label="验收标准">
        <el-input
          v-model="form.acceptance_criteria"
          type="textarea"
          :rows="2"
          placeholder="做到什么算完成（AI 执行前明确，也是验收依据）…"
        />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="截止日期">
            <el-date-picker
              v-model="form.due_date"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              placeholder="选择日期"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="备注">
            <el-input v-model="form.remark" placeholder="补充说明…" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="只读">
        <el-switch
          v-model="form.read_only"
          active-text="开启只读"
          inline-prompt
          :active-value="true"
          :inactive-value="false"
        />
        <div class="form-hint">
          只读卡片不写代码、不产生文件，仅限 AI 读取与讨论（在权限与沙箱上限制）。
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.form-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;
}
</style>
