<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <h1>管理员登录</h1>
        <p>请输入密码访问管理后台</p>
      </div>

      <el-card class="login-card">
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="auto"
          @submit.prevent="handleSubmit"
        >
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入管理员密码"
              show-password
              @keyup.enter="handleSubmit"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              native-type="submit"
              class="login-btn"
            >
              {{ loading ? '登录中...' : '登录' }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { FormInstance, ElMessage } from 'element-plus'

const form = ref({ password: '' })
const loading = ref(false)
const formRef = ref<FormInstance>()
const router = useRouter()
const authStore = useAuthStore()

const rules = {
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 3, message: '密码长度不能少于 3 位', trigger: 'blur' }
  ]
}

const handleSubmit = async () => {
  if (!formRef.value) return

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  const success = await authStore.login(form.value.password)

  if (success) {
    ElMessage.success('登录成功')
    router.push('/admin')
  } else {
    ElMessage.error(authStore.error || '登录失败')
  }

  loading.value = false
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.login-container {
  width: 100%;
  max-width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
  color: white;
}

.login-header h1 {
  font-size: 32px;
  margin-bottom: 10px;
}

.login-header p {
  font-size: 14px;
  opacity: 0.8;
}

.login-card {
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.login-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
}

@media (max-width: 768px) {
  .login-header h1 {
    font-size: 26px;
  }
}
</style>
