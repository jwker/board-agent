<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { FolderOpened } from "@element-plus/icons-vue";

import { useProjectsStore } from "@/stores/projects";

const router = useRouter();
const store = useProjectsStore();

const formRef = ref<FormInstance>();
const submitting = ref(false);

const form = reactive({
  name: "",
  directory: "",
  directoryStatus: "empty" as "existing" | "empty",
  description: "",
  agentMd: `# 项目规范

技术栈、编码规范、禁止改动区域、命令约定…（AI 开工时读取）`,
});

const rules: FormRules = {
  name: [{ required: true, message: "请输入项目名称", trigger: "blur" }],
};

function pickDirectory() {
  ElMessage.info("演示：浏览器不提供系统目录选择器，请直接输入绝对路径");
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  submitting.value = true;
  try {
    const project = await store.addProject({
      name: form.name.trim(),
      description: form.description.trim() || null,
      directory: form.directory.trim() || null,
      directory_status: form.directoryStatus,
      agent_md: form.agentMd.trim() || null,
    });
    ElMessage.success("项目已创建");
    router.push(`/projects/${project.id}/board`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "创建失败");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="new-project">
    <el-page-header content="新建项目" @back="router.push('/')" />

    <el-card class="form-card" shadow="never">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：电商后端代码工程" maxlength="100" show-word-limit />
        </el-form-item>

        <el-form-item label="授权目录">
          <div class="dir-row">
            <el-input
              v-model="form.directory"
              placeholder="/Users/you/dev/…（AI 的工作目录边界）"
            />
            <el-button :icon="FolderOpened" @click="pickDirectory">选择目录</el-button>
          </div>
          <div class="form-hint">AI 只能在此目录内创建/修改文件；删除、覆盖、写目录外需你人工审批。</div>
        </el-form-item>

        <el-form-item label="目录状态">
          <el-radio-group v-model="form.directoryStatus">
            <el-radio value="empty">空目录（从零开始）</el-radio>
            <el-radio value="existing">已有代码库</el-radio>
          </el-radio-group>
          <div class="form-hint">空目录将在 AI 首次执行前自动 git init；AI 完成任务需自动提交。</div>
        </el-form-item>

        <el-form-item label="项目介绍">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="这个项目是做什么的、要达成什么…（存系统，进 AI 简报）"
          />
          <div class="form-hint">成为 AI 的「项目认知」（简报静态部分），每次开工自动带上。</div>
        </el-form-item>

        <el-form-item label="AGENT.md">
          <el-input v-model="form.agentMd" type="textarea" :rows="5" />
          <div class="form-hint">
            将保存为 <b>&lt;授权目录&gt;/AGENT.md</b>，随代码库纳入版本管理；AI 每次开工读取它了解项目规范与约束。留空则不生成。
          </div>
        </el-form-item>

        <div class="form-actions">
          <el-button @click="router.push('/')">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submit">创建并进入</el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.new-project {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.form-card {
  border-radius: 10px;
}
.dir-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.dir-row .el-input {
  flex: 1;
}
.form-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 6px;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
