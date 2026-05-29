import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authAPI } from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const isAuthenticated = ref(false)
  const loading = ref(false)
  const error = ref('')

  const login = async (password: string) => {
    loading.value = true
    error.value = ''
    try {
      const response = await authAPI.login(password)
      const token = response.data.token
      localStorage.setItem('admin_token', token)
      isAuthenticated.value = true
      return true
    } catch (err: any) {
      error.value = err.message || '登录失败'
      isAuthenticated.value = false
      return false
    } finally {
      loading.value = false
    }
  }

  const logout = () => {
    localStorage.removeItem('admin_token')
    isAuthenticated.value = false
    error.value = ''
  }

  const verifyAuth = async () => {
    const token = localStorage.getItem('admin_token')
    if (!token) {
      isAuthenticated.value = false
      return false
    }

    try {
      const response = await authAPI.verify()
      isAuthenticated.value = response.data.valid
      return response.data.valid
    } catch {
      isAuthenticated.value = false
      localStorage.removeItem('admin_token')
      return false
    }
  }

  return {
    isAuthenticated,
    loading,
    error,
    login,
    logout,
    verifyAuth,
  }
})
