<template>
  <div class="home-page">
    <div class="home-container">
      <!-- Header -->
      <div class="page-header">
        <h1 class="page-title">PPT 导出服务</h1>
        <p class="page-subtitle">输入卡密和链接，自动导出 PPT</p>
      </div>

      <!-- Main Form -->
      <el-card class="form-card">
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="auto"
          @submit.prevent="handleSubmit"
        >
          <!-- URL Input -->
          <el-form-item label="AnyGen 链接" prop="url">
            <el-input
              v-model="form.url"
              type="url"
              placeholder="https://www.anygen.io/task/..."
              clearable
            />
          </el-form-item>

          <!-- Email Input -->
          <el-form-item label="接收邮箱" prop="email">
            <el-input
              v-model="form.email"
              type="email"
              placeholder="your@email.com"
              clearable
            />
          </el-form-item>

          <!-- Key Input -->
          <el-form-item label="卡密" prop="key">
            <el-input
              v-model="form.key"
              type="password"
              placeholder="输入您的卡密"
              show-password
            />
          </el-form-item>

          <!-- Submit Button -->
          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading || polling"
              native-type="submit"
              class="submit-btn"
            >
              {{ loading ? '提交中...' : polling ? '导出中，请稍候...' : '开始导出' }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Error Alert -->
      <el-alert
        v-if="error"
        type="error"
        :closable="true"
        class="result-alert"
        @close="error = ''"
      >
        <template #title>
          <div class="alert-content">
            <span>{{ error }}</span>
            <el-button type="danger" link @click="handleRetry">一键重试</el-button>
          </div>
        </template>
      </el-alert>

      <!-- Success Alert -->
      <el-alert
        v-if="result && taskStatus === 'done'"
        title="✓ 导出完成！"
        type="success"
        class="result-alert"
        :closable="false"
      >
        <template #default>
          <a :href="`/api/download/${result.taskId}`" class="download-link">
            <el-button type="success">下载 PPT</el-button>
          </a>
        </template>
      </el-alert>

      <!-- Pending Alert -->
      <el-alert
        v-if="result && taskStatus === 'pending'"
        title="⏳ 排队中，请稍候..."
        type="info"
        class="result-alert"
        :closable="false"
      />

      <!-- Processing Alert -->
      <el-alert
        v-if="result && taskStatus === 'processing'"
        title="⚙️ 正在处理中，请稍候..."
        type="warning"
        class="result-alert"
        :closable="false"
      />

      <!-- Footer Link -->
      <div class="page-footer">
        <RouterLink to="/query">
          <el-button type="text">查询卡密状态 →</el-button>
        </RouterLink>
      </div>
    </div>

    <!-- Tutorial Modal -->
    <el-dialog
      v-model="showTutorial"
      title="使用指南"
      width="600px"
      align-center
      @close="dismissTutorial"
    >
      <div class="tutorial-content">
        <div class="tutorial-item">
          <h4>1. 获取链接</h4>
          <p>访问 AnyGen，找到你要导出的任务，按照以下步骤获取分享链接：</p>
          <img src="/jiaocheng1.jpg" alt="获取分享链接步骤" class="tutorial-image" />
        </div>
        <div class="tutorial-item">
          <h4>2. 填写信息</h4>
          <p>在本应用中粘贴链接、输入邮箱和卡密，系统会自动验证。</p>
          <ul class="step-list">
            <li>粘贴 AnyGen 分享链接</li>
            <li>输入接收邮箱</li>
            <li>输入您的卡密</li>
          </ul>
        </div>
        <div class="tutorial-item">
          <h4>3. 等待完成</h4>
          <p>点击"开始导出"后，系统会在后台处理：</p>
          <ul class="step-list">
            <li>⏳ 排队中 - 任务已提交</li>
            <li>⚙️ 处理中 - 系统正在导出</li>
            <li>✓ 完成 - 可以下载或通过邮件接收</li>
          </ul>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="dismissTutorial">我已了解</el-button>
      </template>
    </el-dialog>

    <!-- URL Format Help Modal -->
    <el-dialog
      v-model="showUrlHelp"
      title="链接格式不正确"
      width="600px"
      align-center
    >
      <div class="tutorial-content">
        <el-alert
          title="请使用正确的 AnyGen 分享链接"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 20px;"
        />
        <div class="tutorial-item">
          <h4>如何获取正确的链接？</h4>
          <p>在 AnyGen 页面中点击「分享」按钮，复制生成的分享链接：</p>
          <img src="/jiaocheng1.jpg" alt="获取分享链接步骤" class="tutorial-image" />
        </div>
        <div class="tutorial-item">
          <h4>正确格式示例</h4>
          <p style="font-family: monospace; background: #f5f7fa; padding: 10px; border-radius: 6px; word-break: break-all;">
            https://www.anygen.io/task/xxx-xxx-PAGE_ID?share_id=数字
          </p>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="showUrlHelp = false">我知道了</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { ElMessage, FormInstance, ElMessageBox } from 'element-plus'
import { exportAPI } from '@/services/api'

const STORAGE_KEY = 'faka_last_form'
const TUTORIAL_KEY = 'faka_tutorial_seen'
const URL_PATTERN = /^https:\/\/www\.anygen\.io\/task\/[a-zA-Z0-9-]+-[a-zA-Z0-9]+\?share_id=\d+$/

const formRef = ref<FormInstance>()
const form = ref({ url: '', email: '', key: '' })
const loading = ref(false)
const error = ref('')
const polling = ref(false)
const result = ref<{ taskId: number; status: string } | null>(null)
const taskStatus = ref('')
const showTutorial = ref(false)
const showUrlHelp = ref(false)
const eventSource = ref<EventSource | null>(null)

const rules = {
  url: [{ required: true, message: '请输入 AnyGen 链接', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  key: [{ required: true, message: '请输入卡密', trigger: 'blur' }]
}

// Load saved form
onMounted(() => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      Object.assign(form.value, JSON.parse(saved))
    }
  } catch {
    // ignore
  }

  if (localStorage.getItem(TUTORIAL_KEY) !== '1') {
    showTutorial.value = true
  }
})

// Cleanup SSE connection
onBeforeUnmount(() => {
  if (eventSource.value) {
    eventSource.value.close()
  }
})

// Save form on change
const saveForm = () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(form.value))
  } catch {
    // ignore
  }
}

const dismissTutorial = () => {
  localStorage.setItem(TUTORIAL_KEY, '1')
  showTutorial.value = false
}

const handleSubmit = async () => {
  // Validate form
  if (!formRef.value) return
  
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    ElMessage.error('请填写完整的表单信息')
    return
  }

  // Validate URL format
  if (!URL_PATTERN.test(form.value.url.trim())) {
    showUrlHelp.value = true
    return
  }

  loading.value = true
  error.value = ''
  result.value = null
  taskStatus.value = ''

  try {
    const res = await exportAPI.submit(
      form.value.key,
      form.value.url.trim(),
      form.value.email.trim()
    )
    result.value = res.data
    taskStatus.value = 'pending'
    polling.value = true
    saveForm()
    connectSSE(res.data.taskId)
    ElMessage.success('任务已提交')
  } catch (err: any) {
    error.value = err.message || '提交失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

const connectSSE = (taskId: number) => {
  let reconnectAttempts = 0
  const maxReconnectAttempts = 5
  const baseReconnectDelay = 3000
  let isConnected = true

  const createConnection = () => {
    const es = new EventSource(`/api/tasks/${taskId}/stream`)

    es.onmessage = (event) => {
      reconnectAttempts = 0
      try {
        const task = JSON.parse(event.data)
        taskStatus.value = task.status || 'unknown'

        if (task.status === 'done') {
          isConnected = false
          polling.value = false
          es.close()
          eventSource.value = null
          ElMessage.success('导出完成')
        } else if (task.status === 'failed') {
          isConnected = false
          error.value = task.error_msg || '导出失败'
          polling.value = false
          es.close()
          eventSource.value = null
          ElMessage.error(error.value)
        }
      } catch {
        // ignore
      }
    }

    es.onerror = () => {
      es.close()
      if (isConnected && reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++
        const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts - 1)
        setTimeout(createConnection, delay)
      } else {
        isConnected = false
        polling.value = false
        eventSource.value = null
        if (reconnectAttempts >= maxReconnectAttempts) {
          error.value = '连接已断开，请刷新页面重试'
        }
      }
    }

    eventSource.value = es
  }

  createConnection()
}

const handleRetry = () => {
  error.value = ''
  result.value = null
  taskStatus.value = ''
  handleSubmit()
}
</script>

<style scoped>
.home-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.home-container {
  width: 100%;
  max-width: 500px;
}

.page-header {
  text-align: center;
  margin-bottom: 40px;
  color: white;
}

.page-title {
  font-size: 36px;
  font-weight: bold;
  margin-bottom: 10px;
}

.page-subtitle {
  font-size: 16px;
  opacity: 0.9;
}

.form-card {
  margin-bottom: 20px;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.input-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.submit-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
}

.result-alert {
  margin-bottom: 20px;
}

.alert-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.download-link {
  text-decoration: none;
}

.page-footer {
  text-align: center;
  margin-top: 20px;
}

.tutorial-content {
  margin: 20px 0;
}

.tutorial-item {
  margin-bottom: 20px;
}

.tutorial-item h4 {
  margin-bottom: 8px;
  font-size: 16px;
  font-weight: 600;
}

.tutorial-item p {
  color: #606266;
  line-height: 1.6;
  margin-bottom: 12px;
}

.tutorial-image {
  width: 100%;
  max-width: 600px;
  height: auto;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  margin-top: 12px;
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
}

.step-list {
  margin-left: 20px;
  margin-top: 8px;
  color: #606266;
  line-height: 1.8;
}

.step-list li {
  margin-bottom: 6px;
  font-size: 14px;
}

@media (max-width: 768px) {
  .page-title {
    font-size: 28px;
  }

  .page-subtitle {
    font-size: 14px;
  }

  .home-container {
    width: 100%;
  }
}
</style>
