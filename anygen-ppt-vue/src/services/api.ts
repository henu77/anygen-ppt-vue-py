import axios from 'axios'
import type { Task, TaskStats, ExportResponse, Key, AuthResponse } from '@/types'

const isDev = import.meta.env.DEV

const apiClient = axios.create({
  baseURL: isDev ? 'http://localhost:8000' : '/',
  timeout: 30000,
  withCredentials: true,
})

// 请求拦截器
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('admin_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// 认证相关
export const authAPI = {
  login: (password: string) =>
    apiClient.post('/api/auth', { password }),
  verify: () =>
    apiClient.get('/api/auth'),
}

// 导出相关
export const exportAPI = {
  submit: (key: string, url: string, email: string) =>
    apiClient.post<ExportResponse>('/api/export', { key, url, email }),
  download: (taskId: number) =>
    `/api/download/${taskId}`,
}

// 任务相关
export const tasksAPI = {
  list: (limit = 50, offset = 0) =>
    apiClient.get('/api/tasks', { params: { limit, offset } }),
  get: (taskId: number) =>
    apiClient.get<Task>(`/api/tasks/${taskId}`),
}

// 查询相关
export const queryAPI = {
  checkKey: (key: string) =>
    apiClient.get('/api/query', { params: { key } }),
}

// 卡密管理相关
export const keysAPI = {
  list: () =>
    apiClient.get('/api/keys'),
  create: (count: number, maxUses: number, isSuper: boolean) =>
    apiClient.post('/api/keys', { count, max_uses: maxUses, is_super: isSuper }),
  update: (id: number, status: string) =>
    apiClient.patch(`/api/keys/${id}`, { status }),
  delete: (id: number) =>
    apiClient.delete(`/api/keys/${id}`),
  batch: (action: string, ids: number[], value?: number) =>
    apiClient.post('/api/keys/batch', { action, ids, value }),
}

// 任务管理相关
export const taskAPI = {
  list: () =>
    apiClient.get('/api/tasks'),
  retry: (taskId: number) =>
    apiClient.post(`/api/retry/${taskId}`),
  cleanup: () =>
    apiClient.post('/api/cleanup'),
}

// 系统设置相关
export const settingsAPI = {
  get: () =>
    apiClient.get('/api/settings'),
  update: (settings: Record<string, any>) =>
    apiClient.put('/api/settings', settings),
}

// 闲鱼登录相关
export const xianyuLoginAPI = {
  getQrCode: () =>
    apiClient.post('/api/xianyu/login'),
  checkLogin: (sessionId: string) =>
    apiClient.post('/api/xianyu/login/check', { sessionId }),
  verifyCookies: (cookies: string) =>
    apiClient.post('/api/xianyu/login/verify', { cookies }),
}

// 闲鱼订单相关
export const xianyuOrdersAPI = {
  list: (accountId: string, status?: string) =>
    apiClient.get('/api/xianyu/orders', { params: { accountId, status } }),
  confirmDelivery: (orderNo: string) =>
    apiClient.post(`/api/xianyu/orders/${orderNo}/confirm-delivery`),
}

// 闲鱼多账户相关
export const xianyuMultiAPI = {
  list: () =>
    apiClient.get('/api/xianyu-multi'),
  bind: (accountId: string, cookies: string) =>
    apiClient.post('/api/xianyu-multi/bind', { accountId, cookies }),
  unbind: (accountId: string) =>
    apiClient.post('/api/xianyu-multi/unbind', { accountId }),
  updateTemplate: (accountId: string, deliveryTemplate: string) =>
    apiClient.post('/api/xianyu-multi/template', { accountId, deliveryTemplate }),
  getOrders: (accountId: string, status?: string) =>
    apiClient.get('/api/xianyu-multi/orders', { params: { accountId, status } }),
}

export default apiClient
