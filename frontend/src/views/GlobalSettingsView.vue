<script setup lang="ts">
import { ArrowRight } from "@element-plus/icons-vue";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import {
  getEmailSettings,
  getNotificationPrefs,
  type EmailSettings,
} from "../api/settings";

const router = useRouter();

const NOTICE_OPTIONS: { key: string; label: string; desc: string }[] = [
  { key: "approval_waiting", label: "等待人工审批", desc: "AI 请求人工审批时" },
  { key: "completed", label: "AI 处理完成", desc: "卡片收尾完成时" },
  { key: "failed", label: "任务失败", desc: "AI 执行失败时" },
  { key: "timeout_rejected", label: "审批超时已拒绝", desc: "审批挂起超时自动拒绝时" },
  { key: "clarify", label: "需要澄清", desc: "缺少信息需要你补充时" },
];

const prefs = ref<Record<string, boolean>>({});
const selectedPrefs = ref<string[]>([]);
const email = ref<EmailSettings>({
  smtp_host: "",
  smtp_port: 465,
  smtp_user: "",
  smtp_pass: "",
  from_addr: "",
  to_addr: "",
});
const emailSaving = ref(false);

onMounted(async () => {
  prefs.value = await getNotificationPrefs();
  selectedPrefs.value = NOTICE_OPTIONS.filter((o) => prefs.value[o.key]).map((o) => o.key);
  email.value = await getEmailSettings();
});

function noticeLabel(key: string): string {
  return NOTICE_OPTIONS.find((o) => o.key === key)?.label ?? key;
}

async function savePrefs(): Promise<void> {
  const next: Record<string, boolean> = {};
  for (const o of NOTICE_OPTIONS) next[o.key] = selectedPrefs.value.includes(o.key);
  const m = await import("../api/settings");
  prefs.value = await m.saveNotificationPrefs(next);
  selectedPrefs.value = NOTICE_OPTIONS.filter((o) => prefs.value[o.key]).map((o) => o.key);
  ElMessage.success("通知设置已保存");
}

async function saveEmail(): Promise<void> {
  emailSaving.value = true;
  try {
    const m = await import("../api/settings");
    email.value = await m.saveEmailSettings(email.value);
    ElMessage.success("邮件设置已保存");
  } finally {
    emailSaving.value = false;
  }
}
</script>

<template>
  <div class="settings">
    <el-page-header content="全局设置" @back="router.push('/')" />

    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-title">大模型</span>
      </template>
      <div class="row-hint">
        全局默认模型与自定义模型管理，API Key 本地配置；项目默认模型在看板内设置。
      </div>
      <el-button type="primary" plain @click="router.push('/settings/llm')">
        管理大模型<el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </el-card>

    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-title">向量检索</span>
      </template>
      <div class="row-hint">
        向量库连接与向量模型配置（Milvus 等）。
      </div>
      <el-button type="primary" plain @click="router.push('/settings/vector')">
        管理向量设置<el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </el-card>

    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-title">通知</span>
      </template>
      <el-checkbox-group v-model="selectedPrefs" class="notice-prefs">
        <el-checkbox v-for="o in NOTICE_OPTIONS" :key="o.key" :value="o.key">
          <span class="pref-label">{{ o.label }}</span>
          <span class="pref-desc">{{ o.desc }}</span>
        </el-checkbox>
      </el-checkbox-group>
      <div class="row-tip">取消勾选后，该类事件不再产生站内通知。审批挂起 30 分钟提醒不受此设置影响。</div>
      <el-button type="primary" plain @click="savePrefs">保存通知设置</el-button>
    </el-card>

    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-title">邮件</span>
      </template>
      <div class="row-hint">用于审批挂起 30 分钟时的提醒邮件（仅此场景）。</div>
      <el-form label-width="110px" label-position="left" class="email-form">
        <el-form-item label="SMTP 服务器">
          <el-input v-model="email.smtp_host" placeholder="smtp.example.com" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="email.smtp_port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="email.smtp_user" placeholder="发信账号" />
        </el-form-item>
        <el-form-item label="密码 / 授权码">
          <el-input v-model="email.smtp_pass" type="password" show-password placeholder="SMTP 授权码" />
        </el-form-item>
        <el-form-item label="发件地址">
          <el-input v-model="email.from_addr" placeholder="noreply@example.com" />
        </el-form-item>
        <el-form-item label="收件邮箱">
          <el-input v-model="email.to_addr" placeholder="你接收提醒的邮箱" />
        </el-form-item>
      </el-form>
      <el-button type="primary" plain :loading="emailSaving" @click="saveEmail">保存邮件设置</el-button>
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
.card-title {
  font-weight: 600;
}
.row-hint {
  font-size: 13px;
  color: #909399;
  margin-bottom: 14px;
  line-height: 1.6;
}
.row-tip {
  font-size: 12px;
  color: #c0c4cc;
  margin: 10px 0 14px;
  line-height: 1.6;
}
.notice-prefs {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}
.pref-label {
  font-size: 14px;
}
.pref-desc {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}
.email-form {
  max-width: 460px;
  margin-bottom: 4px;
}
</style>
