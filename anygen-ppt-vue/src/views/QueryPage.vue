<template>
  <div class="query-page">
    <div class="query-container">
      <div class="page-header">
        <h1 class="page-title">查询卡密状态</h1>
        <p class="page-subtitle">输入卡密查看使用情况</p>
      </div>

      <el-card class="query-card">
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="auto"
          @submit.prevent="handleQuery"
        >
          <el-form-item label="卡密" prop="key">
            <el-input
              v-model="form.key"
              placeholder="输入卡密"
              clearable
              @keyup.enter="handleQuery"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              native-type="submit"
              class="query-btn"
            >
              {{ loading ? '查询中...' : '查询' }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Result Card -->
      <el-card v-if="result" class="result-card">
        <template #header>
          <div class="result-title">
            <span>卡密信息</span>
          </div>
        </template>

        <el-row :gutter="20">
          <el-col :xs="24" :sm="12">
            <div class="info-item">
              <span class="info-label">卡密状态</span>
              <el-tag :type="result.status === 'active' ? 'success' : 'danger'">
                {{ result.status === 'active' ? '正常' : '已禁用' }}
              </el-tag>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12">
            <div class="info-item">
              <span class="info-label">最大使用次数</span>
              <span class="info-value">{{ result.max_uses }}</span>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12">
            <div class="info-item">
              <span class="info-label">已使用次数</span>
              <span class="info-value">{{ result.used_count }}</span>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12">
            <div class="info-item">
              <span class="info-label">剩余次数</span>
              <span class="info-value remaining">{{ result.max_uses - result.used_count }}</span>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- Error Alert -->
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="true"
        class="error-alert"
        @close="error = ''"
      />

      <!-- Back Link -->
      <div class="page-footer">
        <RouterLink to="/">
          <el-button type="text">← 返回首页</el-button>
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { FormInstance, ElMessage } from 'element-plus'
import { queryAPI } from '@/services/api'

const form = ref({ key: '' })
const loading = ref(false)
const error = ref('')
const result = ref<any>(null)
const formRef = ref<FormInstance>()

const rules = {
  key: [{ required: true, message: '请输入卡密', trigger: 'blur' }]
}

const handleQuery = async () => {
  if (!formRef.value) return

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  error.value = ''
  result.value = null

  try {
    const res = await queryAPI.checkKey(form.value.key)
    result.value = res.data
    ElMessage.success('查询成功')
  } catch (err: any) {
    error.value = err.message || '查询失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.query-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.query-container {
  width: 100%;
  max-width: 600px;
}

.page-header {
  text-align: center;
  margin-bottom: 30px;
  color: white;
}

.page-title {
  font-size: 32px;
  font-weight: bold;
  margin-bottom: 10px;
}

.page-subtitle {
  font-size: 14px;
  opacity: 0.8;
}

.query-card {
  margin-bottom: 20px;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.query-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
}

.result-card {
  margin-bottom: 20px;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.result-title {
  font-size: 18px;
  font-weight: 600;
}

.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 12px;
}

.info-label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}

.info-value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.info-value.remaining {
  color: #67c23a;
}

.error-alert {
  margin-bottom: 20px;
}

.page-footer {
  text-align: center;
  margin-top: 30px;
}
@media (max-width: 768px) {
  .page-title {
    font-size: 24px;
  }

  .page-subtitle {
    font-size: 13px;
  }

  .info-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    padding: 12px;
  }

  .info-value {
    font-size: 16px;
  }
}</style>
