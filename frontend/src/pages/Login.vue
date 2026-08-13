<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <el-icon class="login-logo"><Document /></el-icon>
        <h1 class="login-title">智能合同与投标管理平台</h1>
        <p class="login-subtitle">企业级合同生命周期管理系统</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="rules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-button"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <span>版本 {{ APP_VERSION }} · Sprint 2</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import { APP_VERSION } from '@/utils/constants'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const loginFormRef = ref(null)
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!loginFormRef.value) return
  try {
    await loginFormRef.value.validate()
    loading.value = true
    await authStore.login(loginForm)
    ElMessage.success('登录成功')
    // 优先跳转 redirect 参数指定的页面,否则跳转首页
    const redirect = route.query.redirect || '/dashboard'
    router.push(redirect)
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示,这里无需重复
    if (err && err.message && !err.message.includes('validate')) {
      // API 错误已被拦截器处理
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: linear-gradient(135deg, #2c3e50 0%, #1a1a2e 50%, #16213e 100%);
}

.login-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo {
  font-size: 48px;
  color: #409eff;
  margin-bottom: 16px;
}

.login-title {
  font-size: 22px;
  color: #303133;
  margin-bottom: 8px;
}

.login-subtitle {
  font-size: 14px;
  color: #909399;
}

.login-form {
  margin-top: 20px;
}

.login-button {
  width: 100%;
}

.login-footer {
  text-align: center;
  margin-top: 20px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
