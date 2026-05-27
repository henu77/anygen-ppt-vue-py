<template>
  <div class="xianyu-login-container">
    <el-card class="login-card">
      <template #header>
        <div class="card-header">
          <span class="font-semibold">闲鱼账户登录</span>
        </div>
      </template>

      <!-- 步骤指示器 -->
      <el-steps :active="stepIndex" process-status="success" class="mb-8">
        <el-step title="获取二维码" />
        <el-step title="扫码登录" />
        <el-step title="验证Cookie" />
        <el-step title="完成" />
      </el-steps>

      <!-- 步骤 1: 获取二维码 -->
      <div v-if="step === 'qrcode'" class="step-content">
        <el-alert type="info" title="说明" :closable="false" class="mb-6">
          <p>点击下方按钮生成二维码，然后用闲鱼APP扫描登录</p>
        </el-alert>
        <div class="text-center">
          <el-button type="primary" size="large" @click="getQrCode" :loading="loading">
            <el-icon><CirclePlus /></el-icon>
            获取二维码
          </el-button>
        </div>
      </div>

      <!-- 步骤 2: 显示二维码和轮询 -->
      <div v-if="step === 'polling'" class="step-content">
        <el-alert type="warning" title="等待扫码" :closable="false" class="mb-6">
          <p>请使用闲鱼APP扫描下方二维码进行登录（轮询中 {{ pollingCount }} 次）</p>
        </el-alert>

        <div class="qr-container text-center mb-6">
          <div v-if="qrCode" class="qr-code-box">
            <img :src="qrCode" alt="QR Code" class="qr-code-img" />
          </div>
          <div v-else class="text-gray-400">
            <el-icon class="is-loading text-3xl">
              <Loading />
            </el-icon>
            <p class="mt-2">生成二维码中...</p>
          </div>
        </div>

        <div class="text-center">
          <el-button @click="cancelQrCode">取消</el-button>
        </div>
      </div>

      <!-- 步骤 3: 验证 Cookie -->
      <div v-if="step === 'verify'" class="step-content">
        <el-alert type="success" :closable="false" class="mb-6">
          <p>🎉 已获取登录信息，现在需要验证 Cookie 的有效性</p>
        </el-alert>

        <el-form :model="verifyForm" label-width="100px" class="mb-6">
          <el-form-item label="Cookie">
            <el-input
              v-model="verifyForm.cookies"
              type="textarea"
              :rows="4"
              readonly
              class="font-mono text-xs"
            />
          </el-form-item>
        </el-form>

        <div class="flex gap-3 justify-center">
          <el-button @click="step = 'qrcode'">返回</el-button>
          <el-button type="primary" @click="verifyCookies" :loading="loading">
            <el-icon><Check /></el-icon>
            验证 Cookie
          </el-button>
        </div>
      </div>

      <!-- 步骤 4: 成功 -->
      <div v-if="step === 'success'" class="step-content">
        <div class="success-container text-center">
          <el-icon class="success-icon">
            <SuccessFilled />
          </el-icon>
          <p class="success-title">登录成功！</p>
          <p class="success-desc">闲鱼账户已验证，Cookie 有效</p>

          <el-divider />

          <div class="mt-6 mb-6">
            <p class="text-sm text-gray-600 mb-3">您的 Cookie 已保存，可以在闲鱼设置中绑定账户</p>
            <el-button type="primary" @click="resetLogin" size="large">
              <el-icon><Plus /></el-icon>
              继续登录其他账户
            </el-button>
          </div>
        </div>
      </div>

      <!-- 错误提示 -->
      <el-alert v-if="error" type="error" :title="error" :closable="true" @close="error = ''" class="mt-4" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CirclePlus, Loading, Check, SuccessFilled, Plus } from '@element-plus/icons-vue'
import { xianyuLoginAPI } from '@/services/api'

type Step = 'qrcode' | 'polling' | 'verify' | 'success'

const step = ref<Step>('qrcode')
const qrCode = ref('')
const sessionId = ref('')
const cookies = ref('')
const loading = ref(false)
const error = ref('')
const pollingCount = ref(0)
let pollingTimer: NodeJS.Timeout | null = null

const verifyForm = ref({
  cookies: '',
})

const stepIndex = computed(() => {
  const steps: Record<Step, number> = {
    qrcode: 0,
    polling: 1,
    verify: 2,
    success: 3,
  }
  return steps[step.value]
})

const getQrCode = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await xianyuLoginAPI.getQrCode()
    qrCode.value = res.data.qrCode || ''
    sessionId.value = res.data.sessionId || ''
    step.value = 'polling'
    pollingCount.value = 0
    startPolling()
  } catch (err: any) {
    error.value = err.response?.data?.error || '获取二维码失败'
  } finally {
    loading.value = false
  }
}

const startPolling = () => {
  if (pollingTimer) clearTimeout(pollingTimer)

  pollingTimer = setTimeout(async () => {
    try {
      const res = await xianyuLoginAPI.checkLogin(sessionId.value)

      if (res.data.status === 'success') {
        cookies.value = res.data.cookies || ''
        verifyForm.value.cookies = cookies.value
        step.value = 'verify'
      } else if (res.data.status === 'pending') {
        pollingCount.value++
        if (pollingCount.value < 120) {
          // 最多轮询2分钟
          startPolling()
        } else {
          error.value = '登录超时，请重新生成二维码'
          step.value = 'qrcode'
        }
      } else if (res.data.status === 'failed') {
        error.value = res.data.error || '登录失败，请重试'
        step.value = 'qrcode'
      }
    } catch (err: any) {
      error.value = err.response?.data?.error || '轮询失败'
    }
  }, 2000)
}

const cancelQrCode = () => {
  if (pollingTimer) clearTimeout(pollingTimer)
  step.value = 'qrcode'
  qrCode.value = ''
  sessionId.value = ''
}

const verifyCookies = async () => {
  if (!verifyForm.value.cookies.trim()) {
    error.value = 'Cookie 不能为空'
    return
  }

  loading.value = true
  error.value = ''
  try {
    const res = await xianyuLoginAPI.verifyCookies(verifyForm.value.cookies)

    if (res.data.valid) {
      step.value = 'success'
      ElMessage.success('Cookie 验证成功')
    } else {
      error.value = 'Cookie 无效，请重试'
    }
  } catch (err: any) {
    error.value = err.response?.data?.error || 'Cookie 验证失败'
  } finally {
    loading.value = false
  }
}

const resetLogin = () => {
  step.value = 'qrcode'
  qrCode.value = ''
  sessionId.value = ''
  cookies.value = ''
  error.value = ''
  pollingCount.value = 0
  verifyForm.value.cookies = ''
}

onUnmounted(() => {
  if (pollingTimer) clearTimeout(pollingTimer)
})
</script>

<style scoped>
.xianyu-login-container {
  padding: 20px 0;
}

.login-card {
  max-width: 600px;
  margin: 0 auto;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.step-content {
  padding: 20px 0;
}

.qr-container {
  margin: 30px 0;
}

.qr-code-box {
  display: inline-block;
  padding: 20px;
  background: white;
  border: 2px solid #dcdfe6;
  border-radius: 8px;
}

.qr-code-img {
  width: 300px;
  height: 300px;
  image-rendering: pixelated;
}

.success-container {
  padding: 40px 20px;
}

.success-icon {
  font-size: 60px;
  color: #67c23a;
  display: block;
  margin-bottom: 20px;
}

.success-title {
  font-size: 24px;
  font-weight: bold;
  margin: 10px 0;
}

.success-desc {
  font-size: 14px;
  color: #909399;
}
</style>
