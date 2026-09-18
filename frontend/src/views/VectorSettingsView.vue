<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { getVectorSettings, saveVectorSettings, type VectorSettings } from "../api/settings";

const router = useRouter();
const form = ref<VectorSettings>({
  provider: "milvus",
  base_url: "http://localhost:19531",
  api_key: "",
  model: "",
  dims: 0,
});
const saving = ref(false);

onMounted(async () => {
  form.value = await getVectorSettings();
});

async function save(): Promise<void> {
  saving.value = true;
  try {
    form.value = await saveVectorSettings(form.value);
    ElMessage.success("向量设置已保存");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="vector-settings">
    <el-page-header content="向量设置" @back="router.push('/settings')" />

    <el-card shadow="never" class="card">
      <template #header>
        <span class="card-title">向量库与向量模型</span>
      </template>
      <div class="row-hint">
        配置向量库连接与向量化模型（Milvus）。向量模型用于卡片/项目内容的语义检索，需与向量库维度匹配。
      </div>
      <el-form label-width="110px" label-position="left" class="form">
        <el-form-item label="向量库类型">
          <el-select v-model="form.provider" style="width: 240px">
            <el-option label="Milvus" value="milvus" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.base_url" placeholder="http://localhost:19531" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password placeholder="如需鉴权时填写" />
        </el-form-item>
        <el-form-item label="向量模型">
          <el-input v-model="form.model" placeholder="如：bge-m3" />
        </el-form-item>
        <el-form-item label="向量维度">
          <el-input-number v-model="form.dims" :min="0" :max="100000" />
        </el-form-item>
      </el-form>
      <el-button type="primary" plain :loading="saving" @click="save">保存向量设置</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.vector-settings {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.card {
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
.form {
  max-width: 460px;
  margin-bottom: 4px;
}
</style>
