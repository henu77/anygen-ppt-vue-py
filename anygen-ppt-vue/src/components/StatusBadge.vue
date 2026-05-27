<template>
  <el-tag :type="getType()" class="status-badge">
    {{ getLabel() }}
  </el-tag>
</template>

<script setup lang="ts">
interface Props {
  status: string
}

const props = defineProps<Props>()

const labelMap: Record<string, string> = {
  done: '已完成',
  failed: '失败',
  processing: '处理中',
  pending: '待处理',
}

const getType = () => {
  const typeMap: Record<string, any> = {
    done: 'success',
    failed: 'danger',
    processing: 'warning',
    pending: 'info'
  }
  return typeMap[props.status] || 'info'
}

const getLabel = () => {
  return labelMap[props.status] || props.status
}
</script>

<style scoped>
.status-badge {
  font-size: 12px;
  padding: 4px 12px;
}
</style>
})
</script>
