<template>
  <div class="keys-container">
    <!-- 生成新卡密模态框 -->
    <el-dialog v-model="showGenDialog" title="生成新卡密" width="500px">
      <div class="space-y-4">
        <el-form :model="genForm" label-width="100px">
          <el-form-item label="生成数量">
            <el-input-number v-model="genForm.count" :min="1" :max="1000" />
          </el-form-item>
          <el-form-item label="最大使用次数">
            <el-input-number v-model="genForm.maxUses" :min="1" :max="9999" />
          </el-form-item>
          <el-form-item label="超级卡密">
            <el-checkbox v-model="genForm.isSuper" />
            <span class="ml-2 text-xs text-gray-500">不计入用户配额</span>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="showGenDialog = false">取消</el-button>
        <el-button type="primary" @click="handleGenerate" :loading="genLoading">生成</el-button>
      </template>
    </el-dialog>

    <!-- 生成结果显示 -->
    <el-dialog v-model="showResultDialog" title="生成成功" width="600px">
      <div class="space-y-3">
        <el-alert type="success" title="卡密已生成" :closable="false" />
        <div class="bg-gray-50 p-4 rounded-lg border max-h-60 overflow-y-auto">
          <div v-for="(key, idx) in genResult" :key="idx" class="font-mono text-sm py-1">
            {{ key }}
          </div>
        </div>
        <el-button type="primary" @click="copyKeys" style="width: 100%">
          <el-icon><DocumentCopy /></el-icon>
          复制全部
        </el-button>
      </div>
      <template #footer>
        <el-button @click="showResultDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 页面头部 -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">卡密管理</h1>
      <el-button type="primary" @click="showGenDialog = true">
        <el-icon><Plus /></el-icon>
        生成卡密
      </el-button>
    </div>

    <!-- 批量操作栏 -->
    <el-card v-if="selectedKeys.size > 0" class="mb-6">
      <div class="flex items-center gap-4 flex-wrap">
        <span class="text-sm text-gray-600">已选 {{ selectedKeys.size }} 个卡密</span>
        <el-button type="danger" size="small" @click="handleBatchDelete" :loading="batchLoading">
          批量删除
        </el-button>
        <el-button type="success" size="small" @click="handleBatchStatus('enable')" :loading="batchLoading">
          批量启用
        </el-button>
        <el-button size="small" @click="handleBatchStatus('disable')" :loading="batchLoading">
          批量禁用
        </el-button>
        <div class="flex items-center gap-2">
          <span class="text-sm">设置使用次数</span>
          <el-input-number v-model="batchMaxUses" :min="1" :max="9999" size="small" style="width: 100px" />
          <el-button type="warning" size="small" @click="handleBatchMaxUses" :loading="batchLoading">
            应用
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 卡密列表 -->
    <el-card class="keys-card">
      <template #header>
        <div class="card-header">
          <span>卡密列表 ({{ keys.length }})</span>
        </div>
      </template>

      <el-table
        :data="keys"
        stripe
        border
        @selection-change="handleSelectionChange"
        :default-sort="{ prop: 'id', order: 'descending' }"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column prop="key" label="卡密" width="260">
          <template #default="{ row }">
            <div class="flex items-center gap-2">
              <code class="font-mono text-xs truncate max-w-[180px]" :title="row.key">{{ row.key }}</code>
              <el-button link size="small" @click="copySingleKey(row.key)" class="shrink-0">
                <el-icon><DocumentCopy /></el-icon>
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="max_uses" label="最大使用次数" width="120" />
        <el-table-column prop="used_count" label="已使用次数" width="120" />
        <el-table-column prop="is_super" label="类型" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_super" type="success">超级卡密</el-tag>
            <el-tag v-else type="info">普通卡密</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'">
              {{ row.status === 'active' ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" sortable>
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              size="small"
              @click="copySingleKey(row.key)"
            >
              <el-icon><DocumentCopy /></el-icon>
              复制
            </el-button>
            <el-button
              link
              type="primary"
              size="small"
              @click="handleToggleStatus(row.id, row.status)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-popconfirm
              title="确定删除此卡密？关联的任务也会被删除。"
              @confirm="handleDelete(row.id)"
            >
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="keys.length === 0" class="text-center py-12 text-gray-400">
        暂无卡密数据
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentCopy, Plus } from '@element-plus/icons-vue'
import { keysAPI } from '@/services/api'

interface KeyData {
  id: number
  key: string
  max_uses: number
  used_count: number
  is_super: boolean
  status: string
  created_at: string
}

interface GenForm {
  count: number
  maxUses: number
  isSuper: boolean
}

const keys = ref<KeyData[]>([])
const selectedKeys = ref<Set<number>>(new Set())
const loading = ref(false)
const genLoading = ref(false)
const batchLoading = ref(false)
const showGenDialog = ref(false)
const showResultDialog = ref(false)
const genResult = ref<string[]>([])
const batchMaxUses = ref(1)

const genForm = ref<GenForm>({
  count: 1,
  maxUses: 1,
  isSuper: false,
})

const formatTime = (time: string) => {
  return new Date(time).toLocaleString('zh-CN')
}

const loadKeys = async () => {
  loading.value = true
  try {
    const res = await keysAPI.list()
    keys.value = res.data.keys || []
  } catch (error: any) {
    ElMessage.error(error.message || '加载卡密失败')
  } finally {
    loading.value = false
  }
}

const handleGenerate = async () => {
  genLoading.value = true
  try {
    const res = await keysAPI.create(genForm.value.count, genForm.value.maxUses, genForm.value.isSuper)
    genResult.value = res.data.keys || []
    showGenDialog.value = false
    showResultDialog.value = true
    loadKeys()
    ElMessage.success(`已生成 ${genResult.value.length} 个卡密`)
  } catch (error: any) {
    ElMessage.error(error.message || '生成卡密失败')
  } finally {
    genLoading.value = false
  }
}

const copyKeys = () => {
  navigator.clipboard.writeText(genResult.value.join('\n'))
  ElMessage.success('已复制到剪贴板')
}

const copySingleKey = (keyStr: string) => {
  navigator.clipboard.writeText(keyStr)
  ElMessage.success('卡密已复制到剪贴板')
}

const handleToggleStatus = async (id: number, currentStatus: string) => {
  const newStatus = currentStatus === 'active' ? 'disabled' : 'active'
  try {
    await keysAPI.update(id, newStatus)
    loadKeys()
    ElMessage.success('更新成功')
  } catch (error: any) {
    ElMessage.error(error.message || '更新失败')
  }
}

const handleDelete = async (id: number) => {
  try {
    await keysAPI.delete(id)
    loadKeys()
    ElMessage.success('删除成功')
  } catch (error: any) {
    ElMessage.error(error.message || '删除失败')
  }
}

const handleSelectionChange = (selection: KeyData[]) => {
  selectedKeys.value = new Set(selection.map((item) => item.id))
}

const handleBatchDelete = () => {
  ElMessageBox.confirm(
    `确定删除选中的 ${selectedKeys.value.size} 个卡密？关联的任务也会被删除。`,
    '警告',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
  )
    .then(async () => {
      batchLoading.value = true
      try {
        await keysAPI.batch('delete', [...selectedKeys.value])
        selectedKeys.value.clear()
        loadKeys()
        ElMessage.success('批量删除成功')
      } catch (error: any) {
        ElMessage.error(error.message || '批量删除失败')
      } finally {
        batchLoading.value = false
      }
    })
    .catch(() => {})
}

const handleBatchStatus = (action: 'enable' | 'disable') => {
  const label = action === 'enable' ? '启用' : '禁用'
  ElMessageBox.confirm(
    `确定${label}选中的 ${selectedKeys.value.size} 个卡密？`,
    '确认',
    { confirmButtonText: '确认', cancelButtonText: '取消' }
  )
    .then(async () => {
      batchLoading.value = true
      try {
        await keysAPI.batch(action, [...selectedKeys.value])
        selectedKeys.value.clear()
        loadKeys()
        ElMessage.success(`${label}成功`)
      } catch (error: any) {
        ElMessage.error(error.message || `${label}失败`)
      } finally {
        batchLoading.value = false
      }
    })
    .catch(() => {})
}

const handleBatchMaxUses = () => {
  ElMessageBox.confirm(
    `确定将选中的 ${selectedKeys.value.size} 个卡密的使用次数改为 ${batchMaxUses.value} ？`,
    '确认',
    { confirmButtonText: '确认', cancelButtonText: '取消' }
  )
    .then(async () => {
      batchLoading.value = true
      try {
        await keysAPI.batch('set_max_uses', [...selectedKeys.value], batchMaxUses.value)
        selectedKeys.value.clear()
        loadKeys()
        ElMessage.success('使用次数已更新')
      } catch (error: any) {
        ElMessage.error(error.message || '更新使用次数失败')
      } finally {
        batchLoading.value = false
      }
    })
    .catch(() => {})
}

onMounted(() => {
  loadKeys()
})
</script>

<style scoped>
.keys-container {
  padding: 20px 0;
}

.keys-card {
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
