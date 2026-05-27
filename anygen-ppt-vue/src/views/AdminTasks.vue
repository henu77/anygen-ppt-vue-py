<template>
  <div class="tasks-container">
    <!-- 清理PPT 确认对话框 -->
    <el-dialog v-model="showCleanupDialog" title="清理PPT文件" width="400px">
      <p class="text-sm text-red-600 mb-4">
        ⚠️ 此操作将删除所有已下载的PPT文件，且不可恢复。确定要继续吗？
      </p>
      <template #footer>
        <el-button @click="showCleanupDialog = false">取消</el-button>
        <el-button type="danger" @click="handleCleanup" :loading="cleanupLoading">确定清理</el-button>
      </template>
    </el-dialog>

    <!-- 错误详情对话框 -->
    <el-dialog v-model="showErrorDialog" title="错误详情" width="600px">
      <div class="bg-red-50 p-4 rounded-lg border border-red-200 font-mono text-sm whitespace-pre-wrap max-h-60 overflow-y-auto">
        {{ errorMessage }}
      </div>
      <template #footer>
        <el-button @click="showErrorDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 页面头部 -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">任务管理</h1>
      <el-button type="danger" @click="showCleanupDialog = true">
        <el-icon><Delete /></el-icon>
        清理PPT
      </el-button>
    </div>

    <!-- 任务列表 -->
    <el-card class="tasks-card">
      <template #header>
        <div class="card-header">
          <span>任务列表 ({{ tasks.length }})</span>
        </div>
      </template>

      <!-- 任务表格 -->
      <el-table
        :data="tasks"
        stripe
        border
        :default-sort="{ prop: 'id', order: 'descending' }"
        v-loading="loading"
      >
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column prop="key" label="卡密" width="180">
          <template #default="{ row }">
            <code class="font-mono text-xs">{{ row.key }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="url" label="链接" min-width="250">
          <template #default="{ row }">
            <div class="truncate text-gray-600 text-sm" :title="row.url">
              {{ row.url }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ formatStatus(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" sortable>
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'done'"
              link
              type="primary"
              size="small"
              @click="downloadTask(row.id)"
            >
              下载
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              link
              type="warning"
              size="small"
              @click="showError(row.error_msg)"
            >
              查看错误
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              link
              type="danger"
              size="small"
              @click="handleRetry(row.id)"
              :loading="retryingId === row.id"
            >
              {{ retryingId === row.id ? '重试中...' : '重试' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="tasks.length === 0" class="text-center py-12 text-gray-400">
        暂无任务数据
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { taskAPI, exportAPI } from '@/services/api'

interface Task {
  id: number
  key: string
  url: string
  email: string
  status: string
  created_at: string
  error_msg: string | null
}

const tasks = ref<Task[]>([])
const loading = ref(false)
const retryingId = ref<number | null>(null)
const showCleanupDialog = ref(false)
const cleanupLoading = ref(false)
const showErrorDialog = ref(false)
const errorMessage = ref('')

const formatTime = (time: string) => {
  return new Date(time).toLocaleString('zh-CN')
}

const formatStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    pending: '待处理',
    processing: '处理中',
    done: '完成',
    failed: '失败',
  }
  return statusMap[status] || status
}

const getStatusType = (status: string) => {
  const typeMap: Record<string, string> = {
    pending: 'warning',
    processing: 'info',
    done: 'success',
    failed: 'danger',
  }
  return typeMap[status] || 'info'
}

const loadTasks = async () => {
  loading.value = true
  try {
    const res = await taskAPI.list()
    tasks.value = res.data.tasks || []
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '加载任务失败')
  } finally {
    loading.value = false
  }
}

const downloadTask = (taskId: number) => {
  window.open(exportAPI.download(taskId), '_blank')
}

const showError = (error: string | null) => {
  errorMessage.value = error || '无错误信息'
  showErrorDialog.value = true
}

const handleRetry = async (taskId: number) => {
  ElMessageBox.confirm(
    '确定要重试此任务吗？',
    '确认',
    { confirmButtonText: '确认', cancelButtonText: '取消' }
  )
    .then(async () => {
      retryingId.value = taskId
      try {
        await taskAPI.retry(taskId)
        loadTasks()
        ElMessage.success('已重试，请稍候...')
      } catch (error: any) {
        ElMessage.error(error.response?.data?.error || '重试失败')
      } finally {
        retryingId.value = null
      }
    })
    .catch(() => {})
}

const handleCleanup = async () => {
  cleanupLoading.value = true
  try {
    const res = await taskAPI.cleanup()
    showCleanupDialog.value = false
    loadTasks()
    ElMessage.success(`已清理 ${res.data.deletedCount} 个PPT文件`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '清理失败')
  } finally {
    cleanupLoading.value = false
  }
}

onMounted(() => {
  loadTasks()
})
</script>

<style scoped>
.tasks-container {
  padding: 20px 0;
}

.tasks-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
