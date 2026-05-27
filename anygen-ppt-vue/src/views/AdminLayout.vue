<template>
  <el-container class="admin-layout">
    <!-- 移动端遮罩 -->
    <div
      v-if="sidebarOpen"
      class="sidebar-overlay"
      @click="sidebarOpen = false"
    />

    <el-aside class="admin-sidebar" :class="{ 'sidebar-open': sidebarOpen }">
      <div class="sidebar-header">
        <h2>管理后台</h2>
      </div>
      <el-menu
        :default-active="activeIndex"
        class="sidebar-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item index="/admin">
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/admin/keys">
          <span>密钥管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/tasks">
          <span>任务管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/settings">
          <span>系统设置</span>
        </el-menu-item>

        <!-- 闲鱼功能分隔线 -->
        <el-divider class="sidebar-divider" />
        <div class="sidebar-group-title">闲鱼功能</div>

        <el-menu-item index="/admin/xianyu-login">
          <span>账户登录</span>
        </el-menu-item>
        <el-menu-item index="/admin/xianyu-orders">
          <span>订单管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/xianyu-settings">
          <span>多账户设置</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <el-button type="danger" text @click="handleLogout">退出登录</el-button>
      </div>
    </el-aside>

    <el-container class="admin-content">
      <el-header class="admin-header">
        <div class="header-left">
          <el-icon class="mobile-menu-btn" @click="sidebarOpen = !sidebarOpen">
            <Menu />
          </el-icon>
          <span class="header-title">{{ getPageTitle(activeIndex) }}</span>
        </div>
        <div class="header-right">
          <el-dropdown>
            <el-button type="primary" text class="user-btn">
              {{ userName }} <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="admin-main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { Menu, ArrowDown } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const sidebarOpen = ref(false)

const activeIndex = computed(() => {
  const path = route.path
  // 直接返回当前路径作为 activeIndex
  if (
    path === '/admin/keys' ||
    path === '/admin/tasks' ||
    path === '/admin/settings' ||
    path === '/admin/xianyu-login' ||
    path === '/admin/xianyu-orders' ||
    path === '/admin/xianyu-settings'
  ) {
    return path
  }
  return '/admin'
})

const userName = computed(() => {
  return 'Admin'
})

const getPageTitle = (path: string) => {
  const titles: Record<string, string> = {
    '/admin': '仪表盘',
    '/admin/keys': '密钥管理',
    '/admin/tasks': '任务管理',
    '/admin/settings': '系统设置',
    '/admin/xianyu-login': '闲鱼账户登录',
    '/admin/xianyu-orders': '闲鱼订单管理',
    '/admin/xianyu-settings': '闲鱼多账户设置',
  }
  return titles[path] || '管理后台'
}

const handleMenuSelect = (path: string) => {
  router.push(path)
  sidebarOpen.value = false
}

const handleLogout = async () => {
  authStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<style scoped>
.admin-layout {
  height: 100vh;
  background-color: #f5f7fa;
}

/* ---------- 遮罩 ---------- */
.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 998;
}

/* ---------- 侧边栏 ---------- */
.admin-sidebar {
  width: 200px;
  background-color: #fff;
  border-right: 1px solid #dcdfe6;
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: 0;
  height: 100vh;
  z-index: 999;
  transition: transform 0.3s ease;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid #dcdfe6;
  text-align: center;
}

.sidebar-header h2 {
  font-size: 18px;
  margin: 0;
  color: #303133;
}

.sidebar-menu {
  flex: 1;
  border: none;
  overflow-y: auto;
}

.sidebar-divider {
  margin: 10px 0;
}

.sidebar-group-title {
  padding: 12px 20px;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sidebar-footer {
  padding: 15px;
  border-top: 1px solid #dcdfe6;
  text-align: center;
}

/* ---------- 主内容区 ---------- */
.admin-content {
  margin-left: 200px;
  display: flex;
  flex-direction: column;
}

.admin-header {
  background-color: #fff;
  border-bottom: 1px solid #dcdfe6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
  min-height: 56px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title {
  font-size: 16px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mobile-menu-btn {
  display: none;
  font-size: 22px;
  cursor: pointer;
  color: #606266;
  flex-shrink: 0;
}

.user-btn {
  white-space: nowrap;
}

.admin-main {
  padding: 16px;
  overflow-y: auto;
}

/* ============ 移动端 ============ */
@media (max-width: 768px) {
  .mobile-menu-btn {
    display: inline-flex;
  }

  .admin-sidebar {
    transform: translateX(-100%);
  }

  .admin-sidebar.sidebar-open {
    transform: translateX(0);
    box-shadow: 4px 0 20px rgba(0, 0, 0, 0.15);
  }

  .admin-content {
    margin-left: 0 !important;
  }

  .admin-header {
    padding: 0 12px;
  }

  .admin-main {
    padding: 12px;
  }

  .header-title {
    font-size: 15px;
  }
}
</style>
