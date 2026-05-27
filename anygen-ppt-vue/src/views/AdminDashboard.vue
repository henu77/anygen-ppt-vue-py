<template>
  <div class="dashboard-container">
    <!-- Stats Grid -->
    <el-row :gutter="20" class="stats-grid">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card stat-blue">
          <div class="stat-label">总任务</div>
          <div class="stat-value">{{ stats?.total || 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card stat-yellow">
          <div class="stat-label">待处理</div>
          <div class="stat-value">{{ stats?.pending || 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card stat-green">
          <div class="stat-label">已完成</div>
          <div class="stat-value">{{ stats?.done || 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card stat-red">
          <div class="stat-label">失败</div>
          <div class="stat-value">{{ stats?.failed || 0 }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- Recent Tasks -->
    <el-card class="tasks-card">
      <template #header>
        <div class="tasks-title">最近任务</div>
      </template>

      <div v-if="recentTasks.length === 0" class="empty-state">
        <p>暂无任务</p>
      </div>

      <!-- 桌面表格 -->
      <div class="hidden md:block">
        <el-table :data="recentTasks" stripe border class="tasks-table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="email" label="邮箱" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">
                {{ getStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180" />
        </el-table>
      </div>

      <!-- 移动端卡片 -->
      <div class="md:hidden space-y-3">
        <div
          v-for="task in recentTasks"
          :key="task.id"
          class="task-mobile-card"
        >
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs text-gray-400">#{{ task.id }}</span>
            <el-tag :type="getStatusType(task.status)" size="small">
              {{ getStatusLabel(task.status) }}
            </el-tag>
          </div>
          <div class="text-sm text-gray-700 mb-1">{{ task.email }}</div>
          <div class="text-xs text-gray-400">{{ task.created_at }}</div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { tasksAPI } from '@/services/api'
import { ElMessage } from 'element-plus'

const stats = ref<any>(null)
const recentTasks = ref<any[]>([])

const getStatusType = (status: string) => {
  const typeMap: Record<string, any> = {
    done: 'success',
    failed: 'danger',
    processing: 'warning',
    pending: 'info'
  }
  return typeMap[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const labelMap: Record<string, string> = {
    done: '已完成',
    failed: '失败',
    processing: '处理中',
    pending: '待处理'
  }
  return labelMap[status] || status
}

onMounted(async () => {
  try {
    const res = await tasksAPI.list(5, 0)
    stats.value = res.data.stats
    recentTasks.value = res.data.tasks || []
  } catch (err) {
    ElMessage.error('加载数据失败')
  }
})
</script>

<style scoped>
.dashboard-container {
  padding-bottom: 20px;
}

.stats-grid {
  margin-bottom: 30px;
}

.stat-card {
  padding: 24px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  text-align: center;
  color: white;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
}

.stat-blue {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.stat-yellow {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.stat-green {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.stat-red {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.tasks-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.tasks-title {
  font-size: 18px;
  font-weight: 600;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #909399;
}

.tasks-table {
  width: 100%;
}

@media (max-width: 768px) {
  .stat-card {
    min-height: 100px;
    margin-bottom: 12px;
  }

  .stat-value {
    font-size: 24px;
  }
}

.task-mobile-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 14px;
  transition: box-shadow 0.2s;
}

.task-mobile-card:active {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
</style>
