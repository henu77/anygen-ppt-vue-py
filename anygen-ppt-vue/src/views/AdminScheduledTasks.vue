<template>
  <div class="scheduled-tasks-container">
    <div class="mb-6">
      <h1 class="text-2xl font-bold mb-2">定时任务管理</h1>
      <p class="text-sm text-gray-600">管理系统定时任务，查看执行状态和日志</p>
    </div>

    <el-card class="tasks-card">
      <template #header>
        <div class="flex items-center justify-between">
          <span>任务列表 ({{ tasks.length }})</span>
          <el-button @click="loadTasks" :loading="loading" size="small">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <!-- 任务表格 -->
      <div class="overflow-x-auto">
        <el-table :data="tasks" stripe border v-loading="loading">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="name" label="任务名称" min-width="160" />
          <el-table-column prop="task_type" label="类型" width="160">
            <template #default="{ row }">
              <el-tag size="small">{{ taskTypeLabel(row.task_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="关联账户" width="140">
            <template #default="{ row }">
              <span v-if="row.config?.account_id" class="text-xs font-mono">{{ row.config.account_id }}</span>
              <span v-else class="text-gray-400">-</span>
            </template>
          </el-table-column>
          <el-table-column label="间隔(秒)" width="100">
            <template #default="{ row }">
              <span>{{ row.interval_seconds }}s</span>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                v-model="row.enabled"
                @change="(val: boolean) => toggleEnabled(row, val)"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column label="上次执行" min-width="220">
            <template #default="{ row }">
              <div v-if="row.last_run_at">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-xs">{{ formatTime(row.last_run_at) }}</span>
                  <el-tag :type="statusType(row.last_run_status)" size="small">
                    {{ statusLabel(row.last_run_status) }}
                  </el-tag>
                </div>
                <div v-if="row.last_run_message" class="text-xs text-gray-500 truncate" :title="row.last_run_message">
                  {{ row.last_run_message }}
                </div>
              </div>
              <span v-else class="text-gray-400 text-xs">未执行</span>
            </template>
          </el-table-column>
          <el-table-column prop="run_count" label="执行次数" width="80" align="center" />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="runNow(row)" :loading="row._running">
                执行
              </el-button>
              <el-button link type="info" size="small" @click="showLogs(row)">
                日志
              </el-button>
              <el-button link type="danger" size="small" @click="deleteTask(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="tasks.length === 0 && !loading" class="text-center py-12 text-gray-400">
        暂无定时任务，绑定闲鱼账户后会自动创建续期任务
      </div>
    </el-card>

    <!-- 日志弹窗 -->
    <el-dialog v-model="showLogDialog" title="执行日志" width="700px">
      <el-table :data="logs" stripe border max-height="400" v-loading="logsLoading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="消息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.message" :title="row.message">{{ row.message }}</span>
            <span v-else class="text-gray-400">-</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="80">
          <template #default="{ row }">
            <span v-if="row.duration_ms != null">{{ row.duration_ms }}ms</span>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.started_at) }}
          </template>
        </el-table-column>
      </el-table>
      <div v-if="logs.length === 0 && !logsLoading" class="text-center py-8 text-gray-400">
        暂无执行日志
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { scheduledTasksAPI } from '@/services/api'

interface Task {
  id: number
  name: string
  task_type: string
  enabled: boolean
  interval_seconds: number
  config: Record<string, any> | null
  last_run_at: string | null
  last_run_status: string | null
  last_run_message: string | null
  run_count: number
  _running?: boolean
}

interface Log {
  id: number
  task_id: number
  status: string
  message: string | null
  duration_ms: number | null
  started_at: string
}

const tasks = ref<Task[]>([])
const loading = ref(false)
const logs = ref<Log[]>([])
const logsLoading = ref(false)
const showLogDialog = ref(false)

const formatTime = (t: string) => new Date(t).toLocaleString('zh-CN')

const taskTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    xianyu_cookie_renew: '闲鱼Cookie续期',
  }
  return map[type] || type
}

const statusLabel = (s: string | null) => {
  const map: Record<string, string> = { success: '成功', failed: '失败', running: '运行中' }
  return map[s || ''] || s || '-'
}

const statusType = (s: string | null) => {
  const map: Record<string, string> = { success: 'success', failed: 'danger', running: 'warning' }
  return map[s || ''] || 'info'
}

const loadTasks = async () => {
  loading.value = true
  try {
    const res = await scheduledTasksAPI.list()
    tasks.value = (res.data.tasks || []).map((t: Task) => ({ ...t, _running: false }))
  } catch (err: any) {
    ElMessage.error(err.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const toggleEnabled = async (task: Task, val: boolean) => {
  try {
    await scheduledTasksAPI.update(task.id, { enabled: val })
    ElMessage.success(val ? '已启用' : '已暂停')
  } catch (err: any) {
    task.enabled = !val
    ElMessage.error(err.message || '操作失败')
  }
}

const runNow = async (task: Task) => {
  task._running = true
  try {
    await scheduledTasksAPI.runNow(task.id)
    ElMessage.success('任务已触发')
    setTimeout(loadTasks, 2000)
  } catch (err: any) {
    ElMessage.error(err.message || '触发失败')
  } finally {
    task._running = false
  }
}

const deleteTask = async (task: Task) => {
  try {
    await ElMessageBox.confirm(`确定删除任务「${task.name}」吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await scheduledTasksAPI.delete(task.id)
    ElMessage.success('已删除')
    loadTasks()
  } catch (err: any) {
    if (err !== 'cancel') {
      ElMessage.error(err.message || '删除失败')
    }
  }
}

const showLogs = async (task: Task) => {
  showLogDialog.value = true
  logsLoading.value = true
  try {
    const res = await scheduledTasksAPI.getLogs(task.id)
    logs.value = res.data.logs || []
  } catch (err: any) {
    ElMessage.error(err.message || '加载日志失败')
  } finally {
    logsLoading.value = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.scheduled-tasks-container {
  padding: 20px 0;
}

.tasks-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

@media (max-width: 768px) {
  .scheduled-tasks-container {
    padding: 0;
  }
}
</style>
