/**
 * 认证状态管理(Pinia)
 *
 * 仅管理:JWT token / 当前用户 / 登录状态
 * 不放业务数据(合同列表等由各页面自行管理)
 *
 * token 持久化到 localStorage,刷新页面时恢复
 */
import { defineStore } from 'pinia'
import { login as loginApi, getProfile } from '@/api/auth'
import { STORAGE_KEYS, ROLES } from '@/utils/constants'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(STORAGE_KEYS.TOKEN) || '',
    user: JSON.parse(localStorage.getItem(STORAGE_KEYS.USER) || 'null'),
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    role: (state) => state.user?.role || '',
    username: (state) => state.user?.username || '',
    isAdmin: (state) => state.user?.role === ROLES.ADMIN,
    isManager: (state) =>
      state.user?.role === ROLES.ADMIN ||
      state.user?.role === ROLES.CONTRACT_MANAGER,
  },

  actions: {
    /**
     * 登录
     * @param {Object} credentials {username, password}
     */
    async login(credentials) {
      const res = await loginApi(credentials)
      this.token = res.data.access_token
      this.user = res.data.user
      localStorage.setItem(STORAGE_KEYS.TOKEN, this.token)
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(this.user))
      return res.data
    },

    /**
     * 获取当前用户信息(用于刷新页面后恢复)
     */
    async fetchProfile() {
      const res = await getProfile()
      this.user = res.data.user
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(this.user))
      return res.data.user
    },

    /**
     * 退出登录
     */
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem(STORAGE_KEYS.TOKEN)
      localStorage.removeItem(STORAGE_KEYS.USER)
    },
  },
})
