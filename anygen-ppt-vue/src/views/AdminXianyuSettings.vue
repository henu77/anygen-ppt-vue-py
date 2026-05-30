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
                  <el-dropdown-item command="relogin">重新登录</el-dropdown-item>
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
          <div class="auto-delivery-section mt-4">
            <div class="flex items-center justify-between mb-3">
              <span class="info-label">自动发货</span>
              <el-switch
                v-model="account.auto_delivery"
                :active-value="true"
                :inactive-value="false"
                @change="(val) => toggleAutoDelivery(account, val)"
                :disabled="account.status !== 'active'"
              />
            </div>

            <div v-if="account.auto_delivery" class="auto-delivery-config">
              <div class="mb-2">
                <span class="info-label">发货商品</span>
              </div>
              <el-select
                v-model="account.auto_item_id"
                placeholder="选择自动发货的商品"
                clearable
                filterable
                style="width: 100%"
                :loading="account._itemsLoading"
                @visible-change="(visible) => visible && loadItems(account)"
              >
                <el-option
                  v-for="item in (account._items || [])"
                  :key="item.item_id"
                  :label="item.title"
                  :value="item.item_id"
                >
                  <span>{{ item.title }}</span>
                  <span style="float: right; color: #8492a6; font-size: 12px">¥{{ item.price }}</span>
                </el-option>
              </el-select>
              <el-button
                type="primary"
                size="small"
                class="mt-2"
                @click="saveAutoDelivery(account)"
                :loading="account._saving"
              >
                保存配置
              </el-button>
            </div>
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

    <!-- 重新登录对话框 -->
    <el-dialog v-model="showReloginDialog" title="重新登录" width="450px" :close-on-click-modal="false">
      <div class="text-center">
        <el-steps :active="reloginStep" process-status="success" class="mb-6">
          <el-step title="获取二维码" />
          <el-step title="扫码" />
          <el-step title="完成" />
        </el-steps>

        <div v-if="reloginStep === 0">
          <el-button type="primary" size="large" @click="startRelogin" :loading="reloginLoading">
            获取二维码
          </el-button>
        </div>

        <div v-if="reloginStep === 1">
          <el-alert type="info" :closable="false" class="mb-4">请使用闲鱼APP扫描二维码（{{ reloginPollCount }}）</el-alert>
          <div v-if="reloginQrCode" class="qr-box mb-4">
            <img :src="reloginQrCode" alt="QR Code" class="qr-img" />
          </div>
          <el-button @click="cancelRelogin">取消</el-button>
        </div>

        <div v-if="reloginStep === 2">
          <el-icon class="text-5xl text-green-500 mb-4"><SuccessFilled /></el-icon>
          <p class="text-lg font-semibold">重新登录成功！</p>
          <p v-if="reloginNickname" class="text-sm text-gray-500 mt-2">昵称：{{ reloginNickname }}</p>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, ArrowDown, SuccessFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { xianyuMultiAPI, xianyuLoginAPI } from '@/services/api'

interface Account {
  id: number
  account_id: string
  nickname: string | null
  status: string
  error_msg: string | null
  reply_template: string
  delivery_template: string
  auto_delivery: boolean
  auto_item_id: string | null
  created_at: string
  updated_at: string
  _items?: ListedItem[]
  _itemsLoading?: boolean
  _saving?: boolean
}

interface ListedItem {
  item_id: string
  title: string
  price: string
  pic_url: string
  status: string
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

// 重新登录
const showReloginDialog = ref(false)
const reloginStep = ref(0)
const reloginLoading = ref(false)
const reloginAccountId = ref('')
const reloginQrCode = ref('')
const reloginSessionId = ref('')
const reloginCookies = ref('')
const reloginNickname = ref('')
const reloginPollCount = ref(0)
let reloginPollTimer: ReturnType<typeof setTimeout> | null = null

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
  if (command === 'relogin') {
    reloginAccountId.value = account.account_id
    reloginStep.value = 0
    reloginQrCode.value = ''
    reloginSessionId.value = ''
    reloginCookies.value = ''
    reloginNickname.value = ''
    reloginPollCount.value = 0
    showReloginDialog.value = true
  } else if (command === 'edit') {
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

const startRelogin = async () => {
  reloginLoading.value = true
  try {
    const res = await xianyuLoginAPI.getQrCode()
    if (!res.data.qrCode || !res.data.sessionId) {
      ElMessage.error('生成二维码失败')
      return
    }
    reloginQrCode.value = res.data.qrCode
    reloginSessionId.value = res.data.sessionId
    reloginStep.value = 1
    reloginPollCount.value = 0
    pollRelogin()
  } catch (err: any) {
    ElMessage.error(err.message || '获取二维码失败')
  } finally {
    reloginLoading.value = false
  }
}

const pollRelogin = () => {
  if (reloginPollTimer) clearTimeout(reloginPollTimer)
  reloginPollTimer = setTimeout(async () => {
    try {
      const res = await xianyuLoginAPI.checkLogin(reloginSessionId.value)
      if (res.data.status === 'success') {
        reloginCookies.value = res.data.cookies || ''
        // 验证 Cookie
        const verifyRes = await xianyuLoginAPI.verifyCookies(reloginCookies.value)
        if (verifyRes.data.valid) {
          reloginNickname.value = verifyRes.data.nickname || ''
          // 调用 relogin API 更新账户
          await xianyuMultiAPI.relogin(reloginAccountId.value, reloginCookies.value, reloginNickname.value)
          reloginStep.value = 2
          ElMessage.success('重新登录成功')
          refreshAccounts()
        } else {
          ElMessage.error('Cookie 验证失败')
          reloginStep.value = 0
        }
      } else if (['pending', 'waiting', 'scanned'].includes(res.data.status)) {
        reloginPollCount.value++
        if (reloginPollCount.value < 120) {
          pollRelogin()
        } else {
          ElMessage.error('登录超时')
          reloginStep.value = 0
        }
      } else if (res.data.status === 'failed' || res.data.status === 'expired') {
        ElMessage.error(res.data.message || '登录失败')
        reloginStep.value = 0
      }
    } catch (err: any) {
      ElMessage.error(err.message || '轮询失败')
    }
  }, 2000)
}

const cancelRelogin = () => {
  if (reloginPollTimer) clearTimeout(reloginPollTimer)
  showReloginDialog.value = false
  reloginStep.value = 0
}

// ── 自动发货 ──────────────────────────────────────────────

const toggleAutoDelivery = async (account: Account, val: boolean) => {
  try {
    await xianyuMultiAPI.updateAutoDelivery(account.account_id, val, account.auto_item_id || undefined)
    message.value = val ? '自动发货已开启' : '自动发货已关闭'
    messageType.value = 'success'
    refreshAccounts()
  } catch (err: any) {
    // 回滚 UI 状态
    account.auto_delivery = !val
    message.value = err.message || '操作失败'
    messageType.value = 'error'
  }
}

const loadItems = async (account: Account) => {
  if (account._items && account._items.length > 0) return
  account._itemsLoading = true
  try {
    const res = await xianyuMultiAPI.getListedItems(account.account_id)
    account._items = res.data?.items || []
  } catch (err: any) {
    ElMessage.error(err.message || '获取商品列表失败')
    account._items = []
  } finally {
    account._itemsLoading = false
  }
}

const saveAutoDelivery = async (account: Account) => {
  account._saving = true
  try {
    await xianyuMultiAPI.updateAutoDelivery(account.account_id, account.auto_delivery, account.auto_item_id || undefined)
    message.value = '自动发货配置已保存'
    messageType.value = 'success'
    refreshAccounts()
  } catch (err: any) {
    message.value = err.message || '保存失败'
    messageType.value = 'error'
  } finally {
    account._saving = false
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

.auto-delivery-section {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.auto-delivery-config {
  margin-top: 8px;
}

.empty-state {
  grid-column: 1 / -1;
}

.orders-preview {
  max-height: 500px;
  overflow-y: auto;
}

.qr-box {
  display: inline-block;
  padding: 16px;
  background: #fff;
  border: 2px solid #dcdfe6;
  border-radius: 8px;
}

.qr-img {
  width: 260px;
  height: 260px;
  image-rendering: pixelated;
}
</style>
