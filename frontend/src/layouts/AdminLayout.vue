<template>
  <!-- 企业后台管理系统布局:Header + Sidebar + Main -->
  <el-container class="admin-layout">
    <!-- 顶部导航 -->
    <el-header class="admin-header">
      <div class="header-left">
        <el-icon class="header-icon"><Document /></el-icon>
        <span class="header-title">智能合同与投标管理平台</span>
        <el-tag size="small" type="info" class="version-tag">{{ APP_VERSION }}</el-tag>
      </div>
      <div class="header-right">
        <el-dropdown @command="handleCommand">
          <span class="user-info">
            <el-icon><User /></el-icon>
            <span class="username">{{ authStore.username }}</span>
            <el-tag size="small" :type="roleTagType">{{ roleLabel }}</el-tag>
            <el-icon class="arrow"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">
                <el-icon><UserFilled /></el-icon>我的账户
              </el-dropdown-item>
              <el-dropdown-item command="logout" divided>
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-container class="admin-body">
      <!-- 侧边栏菜单 -->
      <el-aside width="220px" class="admin-aside">
        <SidebarMenu />
      </el-aside>

      <!-- 主内容区 -->
      <el-main class="admin-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import SidebarMenu from '@/components/SidebarMenu.vue'
import { useAuthStore } from '@/store/auth'
import { APP_VERSION, ROLE_LABELS, ROLES } from '@/utils/constants'

const authStore = useAuthStore()
const router = useRouter()

const roleLabel = computed(() => ROLE_LABELS[authStore.role] || '未知')
const roleTagType = computed(() => {
  if (authStore.role === ROLES.ADMIN) return 'danger'
  if (authStore.role === ROLES.CONTRACT_MANAGER) return 'warning'
  return 'info'
})

function handleCommand(command) {
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗?', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
      .then(() => {
        authStore.logout()
        ElMessage.success('已退出登录')
        router.push('/login')
      })
      .catch(() => {})
  } else if (command === 'profile') {
    router.push('/profile')
  }
}
</script>

<style scoped>
.admin-layout {
  height: 100vh;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(90deg, #2c3e50 0%, #34495e 100%);
  color: #fff;
  padding: 0 24px;
  height: 60px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon {
  font-size: 24px;
  color: #409eff;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.version-tag {
  margin-left: 4px;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #fff;
  cursor: pointer;
  outline: none;
}

.username {
  font-size: 14px;
}

.arrow {
  font-size: 12px;
}

.admin-body {
  height: calc(100vh - 60px);
}

.admin-aside {
  background-color: #304156;
  overflow-x: hidden;
  overflow-y: auto;
}

.admin-main {
  background-color: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}
</style>
