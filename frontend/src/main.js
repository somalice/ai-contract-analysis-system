/**
 * 应用入口
 *
 * 注册:
 * - Vue 3
 * - Element Plus(完整引入 + 中文 locale)
 * - Element Plus 图标(全局注册)
 * - Pinia(状态管理)
 * - Vue Router(路由)
 * - 全局样式
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/index.css'

const app = createApp(App)

// Pinia(必须在 router 之前注册,因为路由守卫中使用 useAuthStore)
app.use(createPinia())

// 路由
app.use(router)

// Element Plus + 中文语言包
app.use(ElementPlus, { locale: zhCn })

// 全局注册 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
