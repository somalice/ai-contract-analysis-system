/**
 * 路由配置 + 全局守卫
 *
 * 职责:
 * - 路由表定义
 * - 全局前置守卫:JWT 校验 + 角色控制
 * - 前端仅控菜单展示/路由可达性,真正权限校验在后端
 *
 * v1.0.0 信息架构重组:
 * - 路由路径完全不变(确保旧 URL 可访问)
 * - meta.group 标识所属菜单分组,用于侧边栏分组渲染
 * - 路由匹配顺序保持不变(动态 :id 始终在同前缀静态路由之后)
 */
import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/store/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/Login.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      // ============================================================
      // 仪表盘
      // ============================================================
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/pages/Dashboard.vue'),
        meta: { title: '仪表盘', group: 'dashboard' },
      },

      // ============================================================
      // 合同管理(group=contract)
      //   - 合同列表 /contracts
      //   - 合同审核 /reviews
      //   - 合同生成 /generation/create
      // ============================================================
      {
        path: 'contracts',
        name: 'ContractList',
        component: () => import('@/pages/contract/ContractList.vue'),
        meta: { title: '合同列表', group: 'contract' },
      },
      {
        path: 'contracts/upload',
        name: 'ContractUpload',
        component: () => import('@/pages/contract/ContractUpload.vue'),
        meta: { title: '上传合同', group: 'contract' },
      },
      {
        path: 'contracts/:id',
        name: 'ContractDetail',
        component: () => import('@/pages/contract/ContractDetail.vue'),
        meta: { title: '合同详情', group: 'contract' },
      },
      {
        path: 'reviews',
        name: 'ReviewList',
        component: () => import('@/pages/review/ReviewList.vue'),
        meta: { title: '合同审核', group: 'contract' },
      },
      {
        path: 'reviews/:id',
        name: 'ReviewDetail',
        component: () => import('@/pages/review/ReviewDetail.vue'),
        meta: { title: '审核报告', group: 'contract' },
      },
      {
        path: 'generation/create',
        name: 'GenerationCreate',
        component: () => import('@/pages/generation/GenerationCreate.vue'),
        meta: { title: '合同生成', group: 'contract' },
      },
      {
        path: 'generation/history',
        name: 'GenerationHistory',
        component: () => import('@/pages/generation/GenerationHistory.vue'),
        meta: { title: '生成记录', group: 'template' },
      },
      {
        path: 'generation/:id',
        name: 'GenerationDetail',
        component: () => import('@/pages/generation/GenerationDetail.vue'),
        meta: { title: '生成详情', group: 'template' },
      },

      // ============================================================
      // 知识管理(group=knowledge)
      //   - 知识库   /knowledge
      //   - RAG 问答 /knowledge/playground
      // ============================================================
      {
        path: 'knowledge',
        name: 'KnowledgeList',
        component: () => import('@/pages/knowledge/KnowledgeList.vue'),
        meta: { title: '知识库', group: 'knowledge' },
      },
      {
        path: 'knowledge/upload',
        name: 'KnowledgeUpload',
        component: () => import('@/pages/knowledge/KnowledgeUpload.vue'),
        meta: { title: '上传知识', group: 'knowledge', roles: ['admin', 'contract_manager'] },
      },
      {
        path: 'knowledge/playground',
        name: 'RagPlayground',
        component: () => import('@/pages/knowledge/RagPlayground.vue'),
        meta: { title: 'RAG 问答', group: 'knowledge' },
      },
      {
        path: 'knowledge/:id',
        name: 'KnowledgeDetail',
        component: () => import('@/pages/knowledge/KnowledgeDetail.vue'),
        meta: { title: '知识文档详情', group: 'knowledge' },
      },

      // ============================================================
      // 模板中心(group=template)
      //   - 模板中心 /templates
      //   - 生成记录 /generation/history (路由定义在上方 contract 分组中,此处仅菜单归属)
      // ============================================================
      {
        path: 'templates',
        name: 'TemplateList',
        component: () => import('@/pages/template/TemplateList.vue'),
        meta: { title: '模板中心', group: 'template' },
      },
      {
        path: 'templates/upload',
        name: 'TemplateUpload',
        component: () => import('@/pages/template/TemplateUpload.vue'),
        meta: { title: '上传模板', group: 'template', roles: ['admin', 'contract_manager'] },
      },
      {
        path: 'templates/:id',
        name: 'TemplateDetail',
        component: () => import('@/pages/template/TemplateDetail.vue'),
        meta: { title: '模板详情', group: 'template' },
      },

      // ============================================================
      // 招投标管理(group=bid)
      //   - 招标文件 /bids
      //   - 需求解析 /bids/requirement
      //   - 投标文件 /proposals/history
      //   - 投标生成 /proposals/create
      // ============================================================
      {
        path: 'bids',
        name: 'BidList',
        component: () => import('@/pages/bid/BidList.vue'),
        meta: { title: '招标文件', group: 'bid' },
      },
      {
        path: 'bids/upload',
        name: 'BidUpload',
        component: () => import('@/pages/bid/BidUpload.vue'),
        meta: { title: '上传招标文件', group: 'bid' },
      },
      {
        path: 'bids/requirement',
        name: 'BidRequirement',
        component: () => import('@/pages/bid/BidRequirement.vue'),
        meta: { title: '需求解析', group: 'bid' },
      },
      {
        path: 'bids/:id',
        name: 'BidDetail',
        component: () => import('@/pages/bid/BidDetail.vue'),
        meta: { title: '招标文件详情', group: 'bid' },
      },
      {
        path: 'proposals/create',
        name: 'ProposalCreate',
        component: () => import('@/pages/bid/ProposalCreate.vue'),
        meta: { title: '投标生成', group: 'bid' },
      },
      {
        path: 'proposals/history',
        name: 'ProposalList',
        component: () => import('@/pages/bid/ProposalList.vue'),
        meta: { title: '投标文件', group: 'bid' },
      },
      {
        path: 'proposals/:id',
        name: 'ProposalDetail',
        component: () => import('@/pages/bid/ProposalDetail.vue'),
        meta: { title: '投标生成详情', group: 'bid' },
      },

      // ============================================================
      // 系统级配置(group=ai,菜单归入系统管理)
      //   - Prompt 管理 /prompts (admin / contract_manager)
      //   - AI 评估     /evaluation (仅 admin)
      // ============================================================
      {
        path: 'prompts',
        name: 'PromptList',
        component: () => import('@/pages/prompt/PromptList.vue'),
        meta: { title: 'Prompt 管理', group: 'ai', roles: ['admin', 'contract_manager'] },
      },
      {
        path: 'evaluation',
        name: 'EvaluationDashboard',
        component: () => import('@/pages/evaluation/EvaluationDashboard.vue'),
        meta: { title: 'AI 评估', group: 'ai', roles: ['admin'] },
      },

      // ============================================================
      // 系统管理(group=system)
      //   - 操作日志   /logs/operations (仅 admin)
      //   - AI 调用日志 /logs/ai        (仅 admin)
      // ============================================================
      {
        path: 'logs/operations',
        name: 'OperationLog',
        component: () => import('@/pages/log/OperationLog.vue'),
        meta: { title: '操作日志', group: 'system', roles: ['admin'] },
      },
      {
        path: 'logs/ai',
        name: 'AiLog',
        component: () => import('@/pages/log/AiLog.vue'),
        meta: { title: 'AI 调用日志', group: 'system', roles: ['admin'] },
      },

      // ============================================================
      // 个人中心(不在侧边栏菜单,通过顶部头像入口访问)
      // ============================================================
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/pages/Profile.vue'),
        meta: { title: '我的账户' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/pages/NotFound.vue'),
    meta: { requiresAuth: false, title: '404' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ---------- 全局前置守卫 ----------
router.beforeEach(async (to, from, next) => {
  // 设置页面标题
  document.title = to.meta.title
    ? `${to.meta.title} - 智能合同与投标管理平台`
    : '智能合同与投标管理平台'

  const authStore = useAuthStore()

  // 不需要认证的页面(登录页/404)
  if (to.meta.requiresAuth === false) {
    // 已登录用户访问登录页 → 跳转首页
    if (to.name === 'Login' && authStore.isLoggedIn) {
      next('/dashboard')
      return
    }
    next()
    return
  }

  // 需要认证但未登录 → 跳转登录
  if (!authStore.isLoggedIn) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // 已登录但无用户信息(刷新页面后) → 重新加载
  if (authStore.isLoggedIn && !authStore.user) {
    try {
      await authStore.fetchProfile()
    } catch (e) {
      // profile 获取失败(token 过期等)→ 清除登录态,跳转登录
      authStore.logout()
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
  }

  // 角色级路由守卫(Sprint 4 - v0.6.0)
  // meta.roles 声明允许访问的角色;未声明则全部角色可访问
  // 真正权限校验仍在后端(role_required),此处仅做前端体验优化
  if (to.meta.roles && to.meta.roles.length > 0) {
    const userRole = authStore.role
    if (!to.meta.roles.includes(userRole)) {
      ElMessage.warning('当前角色无权访问该页面')
      next('/dashboard')
      return
    }
  }

  next()
})

export default router
