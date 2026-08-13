<template>
  <div class="dashboard page-container">
    <!-- ============================================================
         欢迎区域(v1.0.0 企业级定位)
    ============================================================ -->
    <el-card class="welcome-card mb-20" shadow="hover">
      <div class="welcome-content">
        <el-icon class="welcome-icon"><HomeFilled /></el-icon>
        <div class="welcome-text">
          <h2>欢迎回来,{{ authStore.username }}</h2>
          <p class="welcome-role">
            当前角色:{{ roleLabel }} · 系统版本 {{ APP_VERSION }}
          </p>
          <p class="welcome-desc">
            基于 Flask + LangChain + RAG + Agent + OCR 技术的企业级智能合同与投标管理平台,
            覆盖合同生命周期管理、AI 智能解析、风险审核、自动生成与投标文件智能处理。
          </p>
        </div>
      </div>
    </el-card>

    <!-- ============================================================
         业务中心
    ============================================================ -->
    <div class="section-header">
      <el-icon><Briefcase /></el-icon>
      <span>业务中心</span>
    </div>
    <el-row :gutter="20" class="card-grid">
      <el-col :xs="12" :sm="8" :md="8" :lg="4">
        <el-card class="entry-card entry-blue" shadow="hover" @click="router.push('/contracts')">
          <el-icon class="entry-icon"><Document /></el-icon>
          <h3>合同列表</h3>
          <p>合同上传、解析与生命周期管理</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="4">
        <el-card class="entry-card entry-blue" shadow="hover" @click="router.push('/reviews')">
          <el-icon class="entry-icon"><Warning /></el-icon>
          <h3>合同审核</h3>
          <p>查看 AI 风险审核报告</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="4">
        <el-card class="entry-card entry-blue" shadow="hover" @click="router.push('/knowledge')">
          <el-icon class="entry-icon"><Collection /></el-icon>
          <h3>知识库</h3>
          <p>企业知识文档向量化管理</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="4">
        <el-card class="entry-card entry-blue" shadow="hover" @click="router.push('/knowledge/playground')">
          <el-icon class="entry-icon"><ChatDotRound /></el-icon>
          <h3>RAG 问答</h3>
          <p>基于知识库的智能问答</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="4">
        <el-card class="entry-card entry-blue" shadow="hover" @click="router.push('/bids')">
          <el-icon class="entry-icon"><Tickets /></el-icon>
          <h3>招标文件</h3>
          <p>招标文件解析与投标生成</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8" :lg="4">
        <el-card class="entry-card entry-blue" shadow="hover" @click="router.push('/templates')">
          <el-icon class="entry-icon"><Files /></el-icon>
          <h3>模板中心</h3>
          <p>合同模板管理与生成记录</p>
        </el-card>
      </el-col>
    </el-row>

    <!-- ============================================================
         常用功能(按业务功能组织的快捷入口,AI 作为实现方式)
    ============================================================ -->
    <div class="section-header">
      <el-icon><Star /></el-icon>
      <span>常用功能</span>
    </div>
    <el-row :gutter="20" class="card-grid">
      <el-col :xs="12" :sm="8" :md="8">
        <el-card class="entry-card entry-green" shadow="hover" @click="router.push('/reviews')">
          <el-icon class="entry-icon"><Warning /></el-icon>
          <h3>合同审核</h3>
          <p>合同风险智能审核,自动识别条款风险并生成修改建议</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8">
        <el-card class="entry-card entry-green" shadow="hover" @click="router.push('/knowledge/playground')">
          <el-icon class="entry-icon"><ChatDotRound /></el-icon>
          <h3>RAG 问答</h3>
          <p>基于知识库向量检索的智能问答,精准定位企业知识</p>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="8">
        <el-card class="entry-card entry-green" shadow="hover" @click="router.push('/generation/create')">
          <el-icon class="entry-icon"><MagicStick /></el-icon>
          <h3>合同生成</h3>
          <p>基于模板与 LLM 的合同智能生成,参数填充与条款补充</p>
        </el-card>
      </el-col>
    </el-row>

    <!-- ============================================================
         系统能力(根据角色控制可见性)
    ============================================================ -->
    <div v-if="isManager" class="section-header">
      <el-icon><Setting /></el-icon>
      <span>系统能力</span>
    </div>
    <el-row v-if="isManager" :gutter="20" class="card-grid">
      <el-col v-if="isManager" :xs="12" :sm="8" :md="8">
        <el-card class="entry-card entry-orange" shadow="hover" @click="router.push('/prompts')">
          <el-icon class="entry-icon"><DocumentCopy /></el-icon>
          <h3>Prompt 管理</h3>
          <p>Agent Prompt 模板版本管理与激活控制</p>
        </el-card>
      </el-col>
      <el-col v-if="isAdmin" :xs="12" :sm="8" :md="8">
        <el-card class="entry-card entry-orange" shadow="hover" @click="router.push('/logs/operations')">
          <el-icon class="entry-icon"><Notebook /></el-icon>
          <h3>系统日志</h3>
          <p>操作审计日志与 AI 调用日志查询</p>
        </el-card>
      </el-col>
    </el-row>

    <!-- ============================================================
         系统信息
    ============================================================ -->
    <el-card class="info-card mt-16" shadow="never">
      <template #header>
        <span>系统信息</span>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="系统名称">智能合同与投标管理平台</el-descriptions-item>
        <el-descriptions-item label="系统版本">{{ APP_VERSION }}</el-descriptions-item>
        <el-descriptions-item label="当前用户">{{ authStore.username }}</el-descriptions-item>
        <el-descriptions-item label="用户角色">{{ roleLabel }}</el-descriptions-item>
        <el-descriptions-item label="后端框架">Flask + SQLAlchemy + JWT</el-descriptions-item>
        <el-descriptions-item label="前端框架">Vue3 + Element Plus + Pinia</el-descriptions-item>
        <el-descriptions-item label="AI 引擎">DeepSeek + LangChain + FAISS</el-descriptions-item>
        <el-descriptions-item label="文档处理">pdfplumber + OCR Pipeline</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
/**
 * Dashboard 首页(v1.0.0 企业级升级)
 *
 * 重组内容:
 * - 系统版本 v0.9.0 → v1.0.0
 * - 欢迎区增加平台定位描述
 * - 删除旧的 3 卡片快捷入口(合同管理/上传合同/我的账户)
 * - 新增 3 大模块卡片:业务中心 / 常用功能 / 系统能力
 * - RBAC 权限控制:
 *   - 业务中心 + 常用功能: 所有角色可见
 *   - 系统能力 > Prompt 管理: admin / contract_manager 可见
 *   - 系统能力 > 系统日志: 仅 admin 可见
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { APP_VERSION, ROLE_LABELS } from '@/utils/constants'
import {
  HomeFilled,
  Document,
  Warning,
  Collection,
  ChatDotRound,
  Tickets,
  Files,
  Star,
  MagicStick,
  DocumentCopy,
  Notebook,
  Setting,
  Briefcase,
} from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()

const roleLabel = computed(() => ROLE_LABELS[authStore.role] || '未知')
const isManager = computed(() => authStore.isManager)
const isAdmin = computed(() => authStore.isAdmin)
</script>

<style scoped>
/* ---------- 欢迎区域 ---------- */
.welcome-card {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: none;
}

.welcome-content {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.welcome-icon {
  font-size: 56px;
  color: #409eff;
  flex-shrink: 0;
  margin-top: 4px;
}

.welcome-text h2 {
  font-size: 24px;
  color: #303133;
  margin-bottom: 8px;
}

.welcome-role {
  font-size: 14px;
  color: #606266;
  margin-bottom: 8px;
}

.welcome-desc {
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
  max-width: 800px;
}

/* ---------- 分区标题 ---------- */
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin: 24px 0 16px 0;
}

.section-header .el-icon {
  font-size: 18px;
}

/* ---------- 卡片网格 ---------- */
.card-grid {
  margin-bottom: 8px;
}

.entry-card {
  cursor: pointer;
  text-align: center;
  transition: transform 0.2s, box-shadow 0.2s;
  margin-bottom: 20px;
  border-top: 3px solid transparent;
}

.entry-card:hover {
  transform: translateY(-4px);
}

.entry-icon {
  font-size: 36px;
  margin-bottom: 12px;
}

.entry-card h3 {
  font-size: 15px;
  color: #303133;
  margin-bottom: 8px;
}

.entry-card p {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

/* 色系:业务中心(蓝) */
.entry-blue {
  border-top-color: #409eff;
}
.entry-blue .entry-icon {
  color: #409eff;
}

/* 色系:常用功能(绿) */
.entry-green {
  border-top-color: #67c23a;
}
.entry-green .entry-icon {
  color: #67c23a;
}

/* 色系:系统能力(橙) */
.entry-orange {
  border-top-color: #e6a23c;
}
.entry-orange .entry-icon {
  color: #e6a23c;
}

/* ---------- 系统信息 ---------- */
.info-card {
  margin-top: 20px;
}
</style>
