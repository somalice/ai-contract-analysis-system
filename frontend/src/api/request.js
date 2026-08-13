/**
 * Axios 统一封装
 *
 * 职责:
 * - BaseURL 从环境变量读取
 * - 请求拦截器:自动注入 JWT Authorization 头
 * - 响应拦截器:统一处理 code/message,401 自动跳登录
 * - 页面禁止重复写 Axios,统一走本模块
 *
 * 后端统一响应格式:{code, message, data}
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { STORAGE_KEYS } from '@/utils/constants'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 60000, // 60s(上传合同调用 AI 可能较慢)
})

// ---------- 请求拦截器:注入 JWT ----------
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(STORAGE_KEYS.TOKEN)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ---------- 响应拦截器:统一处理 ----------
request.interceptors.response.use(
  (response) => {
    // Blob 下载响应:跳过 res.code 解析,直接返回 Blob(Hotfix-2)
    // 调用方(createObjectURL)期望直接拿到 Blob,非 {code,message,data} 结构
    if (response.config.responseType === 'blob') {
      return response.data
    }
    const res = response.data
    // 后端统一格式:{code, message, data}
    if (res.code === 200) {
      return res
    }
    // 401:认证失败/Token 过期 → 清除登录态,跳转登录
    if (res.code === 401) {
      localStorage.removeItem(STORAGE_KEYS.TOKEN)
      localStorage.removeItem(STORAGE_KEYS.USER)
      ElMessage.error(res.message || '认证已过期,请重新登录')
      // 延迟跳转,避免在路由守卫中循环
      setTimeout(() => {
        window.location.href = '/login'
      }, 1000)
      return Promise.reject(new Error(res.message || 'Unauthorized'))
    }
    // 其他业务错误:统一提示
    ElMessage.error(res.message || '请求失败')
    return Promise.reject(new Error(res.message || 'Error'))
  },
  (error) => {
    // HTTP 层错误(网络/超时/跨域等)
    let message = '网络错误,请稍后重试'
    if (error.response) {
      const status = error.response.status
      const data = error.response.data
      if (status === 401) {
        localStorage.removeItem(STORAGE_KEYS.TOKEN)
        localStorage.removeItem(STORAGE_KEYS.USER)
        message = data?.message || '认证已过期,请重新登录'
        setTimeout(() => {
          window.location.href = '/login'
        }, 1000)
      } else if (status === 403) {
        message = data?.message || '权限不足'
      } else if (status === 404) {
        message = data?.message || '资源不存在'
      } else if (status >= 500) {
        message = data?.message || '服务器内部错误'
      } else {
        message = data?.message || `请求失败(${status})`
      }
    } else if (error.code === 'ECONNABORTED') {
      message = '请求超时,请稍后重试'
    }
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default request
