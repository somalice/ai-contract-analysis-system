<template>
  <!-- 侧边栏菜单(Sprint 8.10 信息架构重构:以业务功能为一级菜单,AI 能力融入业务) -->
  <el-menu
    :default-active="activeMenu"
    class="sidebar-menu"
    background-color="#304156"
    text-color="#bfcbd9"
    active-text-color="#409eff"
    :unique-opened="true"
    router
  >
    <!-- 首页(顶层独立项) -->
    <el-menu-item index="/dashboard">
      <el-icon><HomeFilled /></el-icon>
      <span>首页</span>
    </el-menu-item>

    <!-- ============================================================
         合同管理
         ├ 合同列表   /contracts
         ├ 合同审核   /reviews(AI 审核能力集成于此)
         └ 合同生成   /generation/create(AI 生成能力集成于此)
    ============================================================ -->
    <el-sub-menu index="contract">
      <template #title>
        <el-icon><Document /></el-icon>
        <span>合同管理</span>
      </template>
      <el-menu-item index="/contracts">
        <el-icon><Document /></el-icon>
        <span>合同列表</span>
      </el-menu-item>
      <el-menu-item index="/reviews">
        <el-icon><Warning /></el-icon>
        <span>合同审核</span>
      </el-menu-item>
      <el-menu-item index="/generation/create">
        <el-icon><MagicStick /></el-icon>
        <span>合同生成</span>
      </el-menu-item>
    </el-sub-menu>

    <!-- ============================================================
         招投标管理
         ├ 招标文件   /bids
         ├ 投标文件   /proposals/history(投标生成记录/文件管理)
         └ 投标生成   /proposals/create(AI 生成能力集成于此)
    ============================================================ -->
    <el-sub-menu index="bid">
      <template #title>
        <el-icon><Tickets /></el-icon>
        <span>招投标管理</span>
      </template>
      <el-menu-item index="/bids">
        <el-icon><Tickets /></el-icon>
        <span>招标文件</span>
      </el-menu-item>
      <el-menu-item index="/proposals/history">
        <el-icon><List /></el-icon>
        <span>投标文件</span>
      </el-menu-item>
      <el-menu-item index="/proposals/create">
        <el-icon><MagicStick /></el-icon>
        <span>投标生成</span>
      </el-menu-item>
    </el-sub-menu>

    <!-- ============================================================
         知识管理
         ├ 知识库   /knowledge
         └ RAG 问答 /knowledge/playground
    ============================================================ -->
    <el-sub-menu index="knowledge">
      <template #title>
        <el-icon><Collection /></el-icon>
        <span>知识管理</span>
      </template>
      <el-menu-item index="/knowledge">
        <el-icon><Collection /></el-icon>
        <span>知识库</span>
      </el-menu-item>
      <el-menu-item index="/knowledge/playground">
        <el-icon><ChatDotRound /></el-icon>
        <span>RAG 问答</span>
      </el-menu-item>
    </el-sub-menu>

    <!-- ============================================================
         系统管理
         - Prompt 管理   /prompts (admin / contract_manager)
         - 模板中心      /templates
         - AI 评估       /evaluation (仅 admin)
         - AI 调用日志   /logs/ai (仅 admin)
         - 操作日志      /logs/operations (仅 admin)
    ============================================================ -->
    <el-sub-menu index="system">
      <template #title>
        <el-icon><Setting /></el-icon>
        <span>系统管理</span>
      </template>
      <el-menu-item v-if="isManager" index="/prompts">
        <el-icon><Notebook /></el-icon>
        <span>Prompt 管理</span>
      </el-menu-item>
      <el-menu-item index="/templates">
        <el-icon><Files /></el-icon>
        <span>模板中心</span>
      </el-menu-item>
      <el-menu-item v-if="isAdmin" index="/evaluation">
        <el-icon><DataLine /></el-icon>
        <span>AI 评估</span>
      </el-menu-item>
      <el-menu-item v-if="isAdmin" index="/logs/ai">
        <el-icon><Monitor /></el-icon>
        <span>AI 调用日志</span>
      </el-menu-item>
      <el-menu-item v-if="isAdmin" index="/logs/operations">
        <el-icon><EditPen /></el-icon>
        <span>操作日志</span>
      </el-menu-item>
    </el-sub-menu>
  </el-menu>
</template>

<script setup>
/**
 * 侧边栏菜单(Sprint 8.10 信息架构重构)
 *
 * 结构(以业务功能为一级菜单,AI 能力融入对应业务):
 * - 首页(独立项)
 * - 合同管理: 合同列表 /contracts · 合同审核 /reviews · 合同生成 /generation/create
 * - 招投标管理: 招标文件 /bids · 投标文件 /proposals/history · 投标生成 /proposals/create
 * - 知识管理: 知识库 /knowledge · RAG 问答 /knowledge/playground
 * - 系统管理: Prompt 管理 /prompts · 模板中心 /templates · AI 评估 /evaluation
 *             · AI 调用日志 /logs/ai · 操作日志 /logs/operations
 *
 * 约束:
 * - 保留所有已有路由,旧 URL 可直接访问(仅调整菜单展示,不修改业务页面)
 * - 用户管理暂无对应路由/页面(简化 RBAC),不在菜单展示
 * - 生成记录 /generation/history 保留旧入口可访问,菜单不单独展示(高亮到模板中心)
 * - 需求解析 /bids/requirement 保留旧入口可访问,菜单不单独展示(高亮到招标文件)
 *
 * 权限控制(与路由守卫 meta.roles 一致):
 * - AI 评估 / AI 调用日志 / 操作日志: 仅 admin(isAdmin)
 * - Prompt 管理: admin / contract_manager(isManager)
 * - 其他菜单项: 所有角色可见
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  HomeFilled,
  Document,
  Collection,
  Warning,
  Tickets,
  List,
  ChatDotRound,
  MagicStick,
  DataLine,
  Setting,
  Notebook,
  Files,
  Monitor,
  EditPen,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'

const route = useRoute()
const authStore = useAuthStore()

const isManager = computed(() => authStore.isManager)
const isAdmin = computed(() => authStore.isAdmin)

// 当前激活的菜单项(根据路由高亮)
// 详情页 / 上传页高亮到所属列表页菜单项
const activeMenu = computed(() => {
  const path = route.path

  // 合同: 上传页 / 详情页 → 合同列表
  if (path.startsWith('/contracts/')) {
    return '/contracts'
  }
  // 审核: 详情页 → 合同审核
  if (path.startsWith('/reviews/')) {
    return '/reviews'
  }
  // 合同生成详情 → 合同生成(/generation/create)
  if (
    path.startsWith('/generation/') &&
    path !== '/generation/create' &&
    path !== '/generation/history'
  ) {
    return '/generation/create'
  }
  // 生成记录 → 模板中心(保留旧入口可访问,菜单不单独展示)
  if (path === '/generation/history') {
    return '/templates'
  }
  // 知识: 上传页 / 详情页 → 知识库(RAG 问答保持独立高亮)
  if (path.startsWith('/knowledge/') && path !== '/knowledge/playground') {
    return '/knowledge'
  }
  // 模板: 上传页 / 详情页 → 模板中心
  if (path.startsWith('/templates/')) {
    return '/templates'
  }
  // 招标: 上传页 / 详情页 / 需求解析 → 招标文件
  if (path.startsWith('/bids/')) {
    return '/bids'
  }
  // 投标生成详情 → 投标生成
  if (path.startsWith('/proposals/') && path !== '/proposals/history') {
    return '/proposals/create'
  }

  return path
})
</script>

<style scoped>
.sidebar-menu {
  border-right: none;
  height: 100%;
}

.sidebar-menu .el-menu-item {
  height: 50px;
  line-height: 50px;
}

.sidebar-menu .el-menu-item:hover {
  background-color: #263445 !important;
}

.sidebar-menu .el-menu-item.is-active {
  background-color: #1f2d3d !important;
}
</style>
