<template>
  <!-- 我的账户页:当前用户信息 + Token 信息 + 退出登录 -->
  <div class="page-container" v-loading="loading">
    <el-card class="mb-16" shadow="never">
      <template #header>
        <div class="card-header">
          <el-icon><User /></el-icon>
          <span>我的账户</span>
        </div>
      </template>

      <template v-if="user">
        <!-- 用户基本信息 -->
        <el-descriptions :column="2" border>
          <el-descriptions-item label="用户ID">
            {{ user.id }}
          </el-descriptions-item>
          <el-descriptions-item label="用户名">
            {{ user.username }}
          </el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag size="small" :type="roleTagType">
              {{ roleLabel }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" type="success">正常</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="注册时间">
            {{ formatTime(user.created_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="最后更新">
            {{ formatTime(user.updated_time) }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-card>

    <!-- Token 信息 -->
    <el-card class="mb-16" shadow="never" v-if="authStore.token">
      <template #header>
        <div class="card-header">
          <el-icon><Key /></el-icon>
          <span>认证凭证(Token)</span>
        </div>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="Token 类型">Bearer (JWT)</el-descriptions-item>
        <el-descriptions-item label="Token 前缀">
          <code class="token-prefix">{{ tokenPrefix }}...</code>
        </el-descriptions-item>
        <el-descriptions-item label="有效期">24 小时(登录时起算)</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 操作 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <el-icon><Setting /></el-icon>
          <span>账户操作</span>
        </div>
      </template>
      <el-button
        type="danger"
        :icon="SwitchButton"
        @click="handleLogout"
      >
        退出登录
      </el-button>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 我的账户页
 *
 * 职责:
 * - 展示当前用户基本信息(用户名 / 角色 / 注册时间)
 * - 展示 Token 信息(前缀,不暴露完整 Token)
 * - 提供退出登录入口
 *
 * 约束:
 * - 不新增修改密码、头像上传等未来 Sprint 功能
 * - 数据来自 authStore(登录时获取)+ fetchProfile(刷新时恢复)
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Key, Setting, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import { ROLE_LABELS, ROLES } from '@/utils/constants'
import { formatTime } from '@/utils/format'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)

const user = computed(() => authStore.user)

const roleLabel = computed(() => ROLE_LABELS[authStore.role] || '未知')
const roleTagType = computed(() => {
  if (authStore.role === ROLES.ADMIN) return 'danger'
  if (authStore.role === ROLES.CONTRACT_MANAGER) return 'warning'
  return 'info'
})

// Token 前缀(仅展示前 20 字符 + ...,不暴露完整 Token)
const tokenPrefix = computed(() => {
  const token = authStore.token
  if (!token) return ''
  return token.substring(0, 20)
})

/**
 * 加载用户信息(确保 created_time 等字段存在)
 */
async function loadProfile() {
  // 如果 store 中已有用户信息且包含 created_time,无需重复请求
  if (authStore.user && authStore.user.created_time) return

  loading.value = true
  try {
    await authStore.fetchProfile()
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示
  } finally {
    loading.value = false
  }
}

/**
 * 退出登录
 */
async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗?', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    authStore.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  } catch {
    // 用户取消
  }
}

onMounted(() => {
  loadProfile()
})
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.token-prefix {
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  color: #606266;
  background-color: #f5f7fa;
  padding: 2px 8px;
  border-radius: 3px;
}
</style>
