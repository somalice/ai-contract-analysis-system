/**
 * 认证 API 模块
 *
 * 对接后端 /api/v1/auth:
 * - POST /auth/login     用户登录
 * - GET  /auth/profile   获取当前用户信息
 * - POST /auth/register  用户注册(管理端暂不提供,预留)
 */
import request from './request'

/**
 * 用户登录
 * @param {Object} credentials {username, password}
 * @returns {Promise<{access_token, user}>}
 */
export function login(credentials) {
  return request.post('/auth/login', credentials)
}

/**
 * 获取当前用户信息(需 JWT)
 * @returns {Promise<{user}>}
 */
export function getProfile() {
  return request.get('/auth/profile')
}

/**
 * 用户注册(预留,Phase A 不在 UI 暴露)
 * @param {Object} data {username, password, role}
 * @returns {Promise<{user}>}
 */
export function register(data) {
  return request.post('/auth/register', data)
}
