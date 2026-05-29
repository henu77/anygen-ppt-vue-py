<template>
  <div class="settings-container">
    <!-- 页面头部 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold mb-2">系统设置</h1>
      <p class="text-sm text-gray-600">配置系统的各项参数，所有更改将立即生效</p>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="text-center py-12">
      <el-icon class="is-loading text-2xl mb-4">
        <Loading />
      </el-icon>
      <p class="text-gray-500">加载中...</p>
    </div>

    <!-- 设置内容 -->
    <div v-else class="space-y-6">
      <!-- AnyGen 导出配置 -->
      <el-card class="settings-card">
        <template #header>
          <div class="card-header">
            <span class="font-semibold">AnyGen 导出配置</span>
          </div>
        </template>

        <el-form :model="form" label-width="150px" class="settings-form">
          <el-form-item label="AnyGen Cookie" required>
            <el-input
              v-model="form.anygen_cookie"
              type="password"
              show-password
              placeholder="粘贴完整的 Cookie"
            />
            <p class="text-xs text-gray-400 mt-2">从 AnyGen 账号获取的完整 Cookie，用于调用 API</p>
          </el-form-item>

          <el-form-item label="代理服务器">
            <el-input
              v-model="form.anygen_proxy"
              placeholder="例如 http://127.0.0.1:7897"
            />
            <p class="text-xs text-gray-400 mt-2">可选，用于加速网络连接（如 Clash 代理）</p>
          </el-form-item>

          <el-form-item label="启用代理">
            <el-switch v-model="form.anygen_use_proxy" />
            <p class="text-xs text-gray-400 ml-3">关闭后即使填写了代理地址也不使用代理，所有请求直连</p>
          </el-form-item>

          <el-form-item label="浏览器无头模式">
            <el-switch v-model="form.playwright_headless" />
            <p class="text-xs text-gray-400 ml-3">勾选则浏览器不显示 UI（推荐勾选）</p>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 超时和性能参数 -->
      <el-card class="settings-card">
        <template #header>
          <div class="card-header">
            <span class="font-semibold">超时和性能参数</span>
          </div>
        </template>

        <el-form :model="form" label-width="150px" class="settings-form">
          <el-form-item label="编辑器加载超时 (秒)">
            <div class="flex items-center gap-3">
              <el-input-number
                v-model="form.editor_wait_seconds"
                :min="60"
                :max="1200"
              />
              <span class="text-xs text-gray-400">范围: 60-1200</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">编辑器加载页面的等待时间</p>
          </el-form-item>

          <el-form-item label="稳定等待时间 (秒)">
            <div class="flex items-center gap-3">
              <el-input-number
                v-model="form.stable_seconds"
                :min="5"
                :max="60"
              />
              <span class="text-xs text-gray-400">范围: 5-60</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">等待页面稳定加载的时间</p>
          </el-form-item>

          <el-form-item label="最小块数 (每页)">
            <div class="flex items-center gap-3">
              <el-input-number
                v-model="form.min_blocks_per_slide"
                :min="1"
                :max="20"
              />
              <span class="text-xs text-gray-400">范围: 1-20</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">每个幻灯片最少包含的块数</p>
          </el-form-item>

          <el-form-item label="导出超时 (秒)">
            <div class="flex items-center gap-3">
              <el-input-number
                v-model="form.export_wait_seconds"
                :min="60"
                :max="1200"
              />
              <span class="text-xs text-gray-400">范围: 60-1200</span>
            </div>
            <p class="text-xs text-gray-400 mt-2">导出 PPT 文件的等待时间</p>
          </el-form-item>

          <el-form-item label="浏览器配置目录">
            <el-input
              v-model="form.playwright_user_data_dir"
              placeholder="data/playwright_profile"
            />
            <p class="text-xs text-gray-400 mt-2">Playwright 浏览器配置和缓存目录</p>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 操作按钮 -->
      <div class="flex items-center gap-3 sticky bottom-0 bg-white py-4 px-6 rounded-lg border shadow-sm">
        <el-button type="primary" @click="handleSave" :loading="saving">
          <el-icon><Check /></el-icon>
          保存设置
        </el-button>
        <el-button @click="handleReset">
          <el-icon><Refresh /></el-icon>
          重置为默认
        </el-button>
        <el-alert
          v-if="saveSuccess"
          type="success"
          title="保存成功"
          :closable="true"
          class="flex-1"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Refresh, Loading } from '@element-plus/icons-vue'
import { settingsAPI } from '@/services/api'

interface SettingsForm {
  anygen_cookie: string
  anygen_proxy: string
  anygen_use_proxy: boolean
  playwright_headless: boolean
  editor_wait_seconds: number
  stable_seconds: number
  min_blocks_per_slide: number
  export_wait_seconds: number
  playwright_user_data_dir: string
}

const loading = ref(false)
const saving = ref(false)
const saveSuccess = ref(false)

const form = ref<SettingsForm>({
  anygen_cookie: '',
  anygen_proxy: '',
  anygen_use_proxy: true,
  playwright_headless: true,
  editor_wait_seconds: 480,
  stable_seconds: 12,
  min_blocks_per_slide: 4,
  export_wait_seconds: 360,
  playwright_user_data_dir: 'data/playwright_profile',
})

const defaultForm = {
  anygen_cookie: '',
  anygen_proxy: '',
  anygen_use_proxy: true,
  playwright_headless: true,
  editor_wait_seconds: 480,
  stable_seconds: 12,
  min_blocks_per_slide: 4,
  export_wait_seconds: 360,
  playwright_user_data_dir: 'data/playwright_profile',
}

const loadSettings = async () => {
  loading.value = true
  try {
    const res = await settingsAPI.get()
    // 后端返回 [{key, value}, ...] 数组，转为扁对象
    const items: Array<{ key: string; value: string | null }> = res.data
    const data: Record<string, string> = {}
    for (const item of items) {
      if (item.value !== null && item.value !== undefined) {
        data[item.key] = item.value
      }
    }

    form.value = {
      anygen_cookie: data.anygen_cookie || '',
      anygen_proxy: data.anygen_proxy || '',
      anygen_use_proxy: data.anygen_use_proxy !== 'false',
      playwright_headless: data.playwright_headless !== 'false',
      editor_wait_seconds: parseInt(data.editor_wait_seconds || '480'),
      stable_seconds: parseInt(data.stable_seconds || '12'),
      min_blocks_per_slide: parseInt(data.min_blocks_per_slide || '4'),
      export_wait_seconds: parseInt(data.export_wait_seconds || '360'),
      playwright_user_data_dir: data.playwright_user_data_dir || 'data/playwright_profile',
    }
  } catch (error: any) {
    ElMessage.error(error.message || '加载设置失败')
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  if (!form.value.anygen_cookie) {
    ElMessage.warning('请输入 AnyGen Cookie')
    return
  }

  ElMessageBox.confirm(
    '确定要保存所有设置更改吗？',
    '确认',
    { confirmButtonText: '保存', cancelButtonText: '取消' }
  )
    .then(async () => {
      saving.value = true
      try {
        const payload = {
          anygen_cookie: form.value.anygen_cookie,
          anygen_proxy: form.value.anygen_proxy,
          anygen_use_proxy: form.value.anygen_use_proxy ? 'true' : 'false',
          playwright_headless: form.value.playwright_headless ? 'true' : 'false',
          editor_wait_seconds: String(form.value.editor_wait_seconds),
          stable_seconds: String(form.value.stable_seconds),
          min_blocks_per_slide: String(form.value.min_blocks_per_slide),
          export_wait_seconds: String(form.value.export_wait_seconds),
          playwright_user_data_dir: form.value.playwright_user_data_dir,
        }

        await settingsAPI.update({ settings: payload })
        ElMessage.success('设置保存成功')
        saveSuccess.value = true
        setTimeout(() => {
          saveSuccess.value = false
        }, 3000)
      } catch (error: any) {
        ElMessage.error(error.message || '保存设置失败')
      } finally {
        saving.value = false
      }
    })
    .catch(() => {})
}

const handleReset = () => {
  ElMessageBox.confirm(
    '确定要重置所有设置为默认值吗？',
    '警告',
    { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' }
  )
    .then(() => {
      form.value = { ...defaultForm }
      ElMessage.success('已重置为默认值，请点击保存按钮保存更改')
    })
    .catch(() => {})
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings-container {
  padding: 20px 0;
}

.settings-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.settings-form {
  margin-top: 20px;
}

@media (max-width: 768px) {
  .settings-container {
    padding: 0;
  }

  .settings-form :deep(.el-form-item__label) {
    width: 120px !important;
  }
}
</style>
