<template>
  <div class="stat-card" :class="colorClass">
    <div class="stat-label">{{ label }}</div>
    <div class="stat-value">{{ value }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  label: string
  value: number
  color?: string
}

const props = withDefaults(defineProps<Props>(), {
  color: 'default',
})

const colorClass = computed(() => {
  const colors: Record<string, string> = {
    yellow: 'bg-yellow',
    green: 'bg-green',
    red: 'bg-red',
  }
  return colors[props.color] || 'bg-default'
})
</script>

<style scoped>
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

.bg-default {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.bg-yellow {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.bg-green {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.bg-red {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}
</style>
