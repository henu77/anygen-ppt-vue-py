<template>
  <div class="xianyu-settings-container">
    <!-- 页面头部 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold mb-2">闲鱼多账户管理</h1>
      <p class="text-sm text-gray-600">管理多个闲鱼账户，绑定和配置账户信息</p>
    </div>

    <!-- 操作提示 -->
    <el-alert v-if="message" :type="messageType" :title="message" :closable="true" @close="message = ''" class="mb-6" />

    <!-- 快速操作 -->
    <el-card class="actions-card mb-6">
      <div class="flex gap-3 flex-wrap">
        <router-link to="/admin/xianyu-login">
          <el-button type="primary">
            <el-icon><Plus /></el-icon>
            新增账户
          </el-button>
        </router-link>
        <el-button @click="refreshAccounts" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </el-card>

    <!-- 账户列表 -->
    <div v-loading="loading" class="accounts-grid">
      <el-card v-for="account in accounts" :key="account.id" class="account-card">
        <!-- 卡片头 -->
        <template #header>
          <div class="account-header">
            <div class="account-title">
              <span class="font-semibold">{{ account.nickname || account.account_id }}</span>
              <el-tag
                :type="getStatusType(account.status)"
                class="ml-3"
              >
                {{ formatStatus(account.status) }}
              </el-tag>
            </div>
            <el-dropdown @command="(cmd) => handleAccountAction(cmd, account)">
              <el-button text type="primary">
                更多 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">编辑模板</el-dropdown-item>
                  <el-dropdown-item command="orders">查看订单</el-dropdown-item>
                  <el-dropdown-item command="unbind" divided>
                    <span class="text-red-600">解绑账户</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>

        <!-- 账户信息 -->
        <div class="account-info">
          <div v-if="account.nickname" class="info-row">
            <span class="info-label">昵称</span>
            <span class="info-value font-semibold">{{ account.nickname }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">账户ID</span>
            <code class="info-value font-mono text-xs">{{ account.account_id }}</code>
          </div>
          <div class="info-row">
            <span class="info-label">创建时间</span>
            <span class="info-value">{{ formatTime(account.created_at) }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">更新时间</span>
            <span class="info-value">{{ formatTime(account.updated_at) }}</span>
          </div>

          <el-divider />

          <!-- 错误信息 -->
          <div v-if="account.error_msg" class="error-box">
            <el-alert
              :title="account.error_msg"
              type="error"
              :closable="false"
            />
          </div>

          <!-- 自动发货状态 -->
          <div class="auto-delivery-status mt-4">
            <el-tag :type="account.auto_delivery ? 'success' : 'info'">
              {{ account.auto_delivery ? '✓ 自动发货已启用' : '○ 自动发货未启用' }}
            </el-tag>
          </div>
        </div>
      </el-card>

      <!-- 空状态 -->
      <div v-if="accounts.length === 0 && !loading" class="empty-state col-span-full text-center py-12">
        <el-empty description="暂无账户" />
        <router-link to="/admin/xianyu-login">
          <el-button type="primary" class="mt-4">
            <el-icon><Plus /></el-icon>
            添加第一个账户
          </el-button>
        </router-link>
      </div>
    </div>

    <!-- 编辑模板对话框 -->
    <el-dialog v-model="showTemplateDialog" title="编辑发货模板" width="600px">
      <el-form :model="templateForm" label-width="100px">
        <el-form-item label="账户ID">
          <el-input v-model="templateForm.accountId" disabled />
        </el-form-item>
        <el-form-item label="发货模板">
          <el-input
            v-model="templateForm.deliveryTemplate"
            type="textarea"
            :rows="6"
            placeholder="输入发货时要发送的消息模板"
          />
          <p class="text-xs text-gray-500 mt-2">支持变量: {key} 卡密, {buyer} 买家名, {amount} 金额</p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTemplateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTemplate" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看订单对话框 -->
    <el-dialog v-model="showOrdersDialog" title="账户订单" width="800px">
      <div class="orders-preview">
        <el-table :data="accountOrders" stripe border max-height="400">
          <el-table-column prop="order_no" label="订单号" width="150">
            <template #default="{ row }">
              <code class="font-mono text-xs">{{ row.order_no }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="buyer_nick" label="买家" width="120" />
          <el-table-column prop="amount" label="金额" width="80" align="right">
            <template #default="{ row }">
              <span v-if="row.amount">¥{{ (row.amount / 100).toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getOrderStatusType(row.status)">
                {{ formatOrderStatus(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="150">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
        <div v-if="accountOrders.length === 0" class="text-center py-8 text-gray-400">
          暂无订单
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, ArrowDown } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { xianyuMultiAPI } from '@/services/api'

interface Account {
  id: number
  account_id: string
  nickname: string | null
  status: string
  error_msg: string | null
  reply_template: string
  delivery_template: string
  auto_delivery: number
  created_at: string
  updated_at: string
}

interface Order {
  id: number
  order_no: string
  buyer_nick: string | null
  amount: number | null
  status: string
  created_at: string
}

const router = useRouter()
const accounts = ref<Account[]>([])
const loading = ref(false)
const saving = ref(false)
const message = ref('')
const messageType = ref<'success' | 'error'>('success')

// 模板编辑对话框
const showTemplateDialog = ref(false)
const templateForm = ref({
  accountId: '',
  deliveryTemplate: '',
})

// 订单查看对话框
const showOrdersDialog = ref(false)
const accountOrders = ref<Order[]>([])

const formatTime = (time: string) => {
  return new Date(time).toLocaleString('zh-CN')
}

const formatStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    disconnected: '未连接',
    connecting: '连接中',
    connected: '已连接',
    error: '错误',
  }
  return statusMap[status] || status
}

const getStatusType = (status: string) => {
  const typeMap: Record<string, string> = {
    disconnected: 'info',
    connecting: 'warning',
    connected: 'success',
    error: 'danger',
  }
  return typeMap[status] || 'info'
}

const formatOrderStatus = (status: string) => {
  const statusMap: Record<string, string> = {
    pending: '待支付',
    paid: '已支付',
    delivered: '已发货',
    completed: '已完成',
  }
  return statusMap[status] || status
}

const getOrderStatusType = (status: string) => {
  const typeMap: Record<string, string> = {
    pending: 'warning',
    paid: 'info',
    delivered: 'success',
    completed: 'success',
  }
  return typeMap[status] || 'info'
}

const refreshAccounts = async () => {
  loading.value = true
  try {
    const res = await xianyuMultiAPI.list()
    accounts.value = res.data.accounts || []
  } catch (err: any) {
    message.value = err.message || '加载账户失败'
    messageType.value = 'error'
  } finally {
    loading.value = false
  }
}

const handleAccountAction = (command: string, account: Account) => {
  if (command === 'edit') {
    templateForm.value.accountId = account.account_id
    templateForm.value.deliveryTemplate = account.delivery_template || ''
    showTemplateDialog.value = true
  } else if (command === 'orders') {
    loadAccountOrders(account.account_id)
  } else if (command === 'unbind') {
    ElMessageBox.confirm(
      `确定要解绑账户 ${account.nickname || account.account_id} 吗？此操作不可恢复。`,
      '警告',
      { confirmButtonText: '解绑', cancelButtonText: '取消', type: 'warning' }
    )
      .then(async () => {
        try {
          await xianyuMultiAPI.unbind(account.account_id)
          message.value = '账户已解绑'
          messageType.value = 'success'
          refreshAccounts()
        } catch (err: any) {
          message.value = err.message || '解绑失败'
          messageType.value = 'error'
        }
      })
      .catch(() => {})
  }
}

const saveTemplate = async () => {
  if (!templateForm.value.deliveryTemplate.trim()) {
    ElMessage.warning('发货模板不能为空')
    return
  }

  saving.value = true
  try {
    await xianyuMultiAPI.updateTemplate(
      templateForm.value.accountId,
      templateForm.value.deliveryTemplate
    )
    message.value = '模板已保存'
    messageType.value = 'success'
    showTemplateDialog.value = false
    refreshAccounts()
  } catch (err: any) {
    message.value = err.message || '保存模板失败'
    messageType.value = 'error'
  } finally {
    saving.value = false
  }
}

const loadAccountOrders = async (accountId: string) => {
  try {
    const res = await xianyuMultiAPI.getOrders(accountId)
    accountOrders.value = res.data.orders || []
    showOrdersDialog.value = true
  } catch (err: any) {
    message.value = err.message || '加载订单失败'
    messageType.value = 'error'
  }
}

onMounted(() => {
  refreshAccounts()
})
</script>

<style scoped>
.xianyu-settings-container {
  padding: 20px 0;
}

.actions-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}

.accounts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.account-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  transition: box-shadow 0.3s ease;
}

.account-card:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.account-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.account-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.account-info {
  padding: 0;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-weight: 500;
  color: #909399;
  font-size: 12px;
}

.info-value {
  color: #303133;
}

.error-box {
  margin-top: 12px;
}

.auto-delivery-status {
  display: flex;
  justify-content: center;
}

.empty-state {
  grid-column: 1 / -1;
}

.orders-preview {
  max-height: 500px;
  overflow-y: auto;
}
</style>
