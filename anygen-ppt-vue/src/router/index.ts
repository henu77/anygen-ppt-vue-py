import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomePage.vue'),
  },
  {
    path: '/query',
    name: 'Query',
    component: () => import('@/views/QueryPage.vue'),
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginPage.vue'),
  },
  {
    path: '/admin',
    name: 'AdminLayout',
    component: () => import('@/views/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'AdminDashboard',
        component: () => import('@/views/AdminDashboard.vue'),
      },
      {
        path: 'keys',
        name: 'AdminKeys',
        component: () => import('@/views/AdminKeys.vue'),
      },
      {
        path: 'tasks',
        name: 'AdminTasks',
        component: () => import('@/views/AdminTasks.vue'),
      },
      {
        path: 'settings',
        name: 'AdminSettings',
        component: () => import('@/views/AdminSettings.vue'),
      },
      {
        path: 'xianyu-login',
        name: 'AdminXianyuLogin',
        component: () => import('@/views/AdminXianyuLogin.vue'),
      },
      {
        path: 'xianyu-orders',
        name: 'AdminXianyuOrders',
        component: () => import('@/views/AdminXianyuOrders.vue'),
      },
      {
        path: 'xianyu-settings',
        name: 'AdminXianyuSettings',
        component: () => import('@/views/AdminXianyuSettings.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth) {
    const isAuth = await authStore.verifyAuth()
    if (!isAuth) {
      next('/login')
      return
    }
  }

  next()
})

export default router
