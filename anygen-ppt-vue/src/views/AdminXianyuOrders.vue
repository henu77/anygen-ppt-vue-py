<template>
  <div class="xianyu-orders-container">
    <!-- 页面头部 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold mb-2">闲鱼订单管理</h1>
      <p class="text-sm text-gray-600">查看和管理闲鱼订单，确认发货信息</p>
    </div>

    <!-- 查询表单 -->
    <el-card class="query-card mb-6">
      <template #header>
        <span>查询订单</span>
      </template>

      <el-form :model="queryForm" label-width="100px" class="query-form">
        <el-row :gutter="20">
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="账号ID">
              <el-input
                v-model="queryForm.accountId"
                placeholder="输入闲鱼账号ID"
                clearable
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="订单状态">
              <el-select v-model="queryForm.status" placeholder="全部状态" clearable>
                <el-option label="待支付" value="pending" />
                <el-option label="已支付" value="paid" />
                <el-option label="已发货" value="delivered" />
                <el-option label="已完成" value="completed" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-button type="primary" @click="fetchOrders" :loading="loading">
              <el-icon><Search /></el-icon>
              查询订单
            </el-button>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 订单统计 -->
    <div v-if="stats" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 md:gap-4 mb-6">
      <el-card class="stat-card">
        <template #header>
          <div class="stat-title">总计</div>
        </template>
        <div class="stat-value">{{ stats.total }}</div>
      </el-card>
      <el-card class="stat-card">
        <template #header>
          <div class="stat-title">待支付</div>
        </template>
        <div class="stat-value text-yellow-600">{{ stats.pending }}</div>
      </el-card>
      <el-card class="stat-card">
        <template #header>
          <div class="stat-title">已支付</div>
        </template>
        <div class="stat-value text-blue-600">{{ stats.paid }}</div>
      </el-card>
      <el-card class="stat-card">
        <template #header>
          <div class="stat-title">已发货</div>
        </template>
        <div class="stat-value text-green-600">{{ stats.delivered }}</div>
      </el-card>
      <el-card class="stat-card">
        <template #header>
          <div class="stat-title">已完成</div>
        </template>
        <div class="stat-value text-cyan-600">{{ stats.completed }}</div>
      </el-card>
    </div>

    <!-- 订单列表 -->
    <el-card class="orders-card">
      <template #header>
        <div class="card-header">
          <span>订单列表 ({{ orders.length }})</span>
        </div>
      </template>

      <!-- 桌面表格 -->
      <div class="hidden md:block overflow-x-auto">
      <el-table
        :data="orders"
        stripe
        border
        v-loading="loading"
        :default-sort="{ prop: 'id', order: 'descending' }"
      >
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column prop="order_no" label="订单号" width="180">
          <template #default="{ row }">
            <code class="font-mono text-xs">{{ row.order_no }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="buyer_nick" label="买家昵称" width="150" />
        <el-table-column prop="amount" label="金额(元)" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.amount">{{ (row.amount / 100).toFixed(2) }}</span>
            <span v-else class="text-gray-400">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="订单状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ formatStatus(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="key_sent" label="密钥发送" width="100">
          <template #default="{ row }">
            <el-tag :type="row.key_sent ? 'success' : 'info'">
              {{ row.key_sent ? '已发送' : '未发送' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="delivery_confirmed" label="发货确认" width="100">
          <template #default="{ row }">
            <el-tag :type="row.delivery_confirmed ? 'success' : 'info'">
              {{ row.delivery_confirmed ? '已确认' : '未确认' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" sortable>
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status !== 'completed' && !row.delivery_confirmed"
              link
              type="primary"
              size="small"
              @click="confirmDelivery(row.order_no)"
              :loading="confirmingOrderNo === row.order_no"
            >
              确认发货
            </el-button>
            <span v-else class="text-gray-400 text-xs">无操作</span>
          </template>
        </el-table-column>
      </el-table>
      </div>

      <!-- 移动端卡片 -->
      <div class="md:hidden space-y-3">
        <div
          v-for="order in orders"
          :key="order.id"
          class="order-mobile-card"
        >
          <div class="flex items-center justify-between mb-2">
            <code class="font-mono text-xs text-gray-600">{{ order.order_no }}</code>
            <el-tag :type="getStatusType(order.status)" size="small">
              {{ formatStatus(order.status) }}
            </el-tag>
          </div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-700">{{ order.buyer_nick || '未知买家' }}</span>
            <span v-if="order.amount" class="text-sm font-semibold">¥{{ (order.amount / 100).toFixed(2) }}</span>
          </div>
          <div class="flex items-center gap-3 text-xs text-gray-500 mb-2">
            <el-tag :type="order.key_sent ? 'success' : 'info'" size="small">
              {{ order.key_sent ? '已发密钥' : '未发密钥' }}
            </el-tag>
            <el-tag :type="order.delivery_confirmed ? 'success' : 'info'" size="small">
              {{ order.delivery_confirmed ? '已确认' : '未确认' }}
            </el-tag>
          </div>
          <div class="text-xs text-gray-400">{{ formatTime(order.created_at) }}</div>
          <div v-if="order.status !== 'completed' && !order.delivery_confirmed" class="mt-2 pt-2 border-t border-gray-100">
            <el-button
              size="small"
              type="primary"
              @click="confirmDelivery(order.order_no)"
              :loading="confirmingOrderNo === order.order_no"
            >
              确认发货
            </el-button>
          </div>
        </div>
      </div>

      <div v-if="orders.length === 0" class="text-center py-12 text-gray-400">
        暂无订单数据
      </div>
    </el-card>

    <!-- 错误提示 -->
    <el-alert v-if="error" type="error" :title="error" :closable="true" @close="error = ''" class="mt-4" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { xianyuOrdersAPI } from '@/services/api'

interface Order {
  id: number
  order_no: string
  buyer_nick: string | null
  amount: number | null
  status: string
  key_sent: number
  delivery_confirmed: number
  created_at: string
}

interface Stats {
  total: number
  pending: number
  paid: number
  delivered: number
  completed: number
}

const queryForm = ref({
  accountId: '',
  status: '',
})

const orders = ref<Order[]>([])
const stats = ref<Stats | null>(null)
const loading = ref(false)
const error = ref('')
const confirmingOrderNo = ref<string>('')

const formatTime = (time: string) => {
  return new Date(time).toLocaleString('zh-CN')
}

const formatStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    pending: '待支付',
    paid: '已支付',
    delivered: '已发货',
    completed: '已完成',
  }
  return statusMap[status] || status
}

const getStatusType = (status: string) => {
  const typeMap: Record<string, string> = {
    pending: 'warning',
    paid: 'info',
    delivered: 'success',
    completed: 'success',
  }
  return typeMap[status] || 'info'
}

const fetchOrders = async () => {
  if (!queryForm.value.accountId.trim()) {
    error.value = '请输入账号 ID'
    return
  }

  loading.value = true
  error.value = ''
  try {
    const res = await xianyuOrdersAPI.list(queryForm.value.accountId, queryForm.value.status || undefined)
    orders.value = res.data.orders || []
    stats.value = res.data.stats || null
  } catch (err: any) {
    error.value = err.response?.data?.error || '加载订单失败'
  } finally {
    loading.value = false
  }
}

const confirmDelivery = async (orderNo: string) => {
  ElMessageBox.confirm(
    '确定要确认此订单的发货吗？',
    '确认',
    { confirmButtonText: '确认', cancelButtonText: '取消' }
  )
    .then(async () => {
      confirmingOrderNo.value = orderNo
      try {
        await xianyuOrdersAPI.confirmDelivery(orderNo)
        fetchOrders()
        ElMessage.success('发货已确认')
      } catch (err: any) {
        error.value = err.response?.data?.error || '确认发货失败'
      } finally {
        confirmingOrderNo.value = ''
      }
    })
    .catch(() => {})
}
</script>

<style scoped>
.xianyu-orders-container {
  padding: 20px 0;
}

.query-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.query-form {
  margin-top: 20px;
}

.stat-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.stat-title {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  margin-top: 8px;
}

.orders-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 移动端卡片 */
.order-mobile-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 14px;
  transition: box-shadow 0.2s;
}

.order-mobile-card:active {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

@media (max-width: 768px) {
  .xianyu-orders-container {
    padding: 0;
  }

  .stat-value {
    font-size: 20px;
  }
}
</style>
