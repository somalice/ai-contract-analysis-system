<template>
  <!-- 投标生成详情页:生成信息 / AI 章节 / RAG 引用 / 校验结果 / Agent Trace / 下载 -->
  <div class="page-container" v-loading="loading">
    <!-- 顶部操作栏 -->
    <el-card class="action-card mb-16" shadow="never">
      <div class="action-bar">
        <el-button :icon="Back" @click="router.back()">返回</el-button>
        <div class="action-right">
          <el-button
            v-if="proposal?.bid"
            :icon="Document"
            @click="goBid"
          >
            查看招标文件
          </el-button>
          <el-button
            v-if="proposal?.status === 'success'"
            type="primary"
            :icon="Download"
            @click="handleDownload"
          >
            下载 Word
          </el-button>
        </div>
      </div>
    </el-card>

    <template v-if="proposal">
      <!-- 状态总览 -->
      <el-card class="mb-16 status-overview" shadow="never" :class="overviewCardClass">
        <div class="overview-content">
          <div class="overview-left">
            <div class="overview-label">生成状态</div>
            <div class="overview-level">
              <el-tag
                :type="PROPOSAL_STATUS_TAG_TYPES[proposal.status] || 'info'"
                effect="dark"
                size="large"
              >
                {{ PROPOSAL_STATUS_LABELS[proposal.status] || proposal.status }}
              </el-tag>
            </div>
          </div>
          <div class="overview-right">
            <div class="overview-stat">
              <span class="stat-label">章节</span>
              <span class="stat-value">{{ proposal.generated_sections?.length || 0 }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">RAG 命中</span>
              <span class="stat-value info">{{ proposal.rag_references?.length || 0 }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">迭代次数</span>
              <span class="stat-value">{{ proposal.iterations ?? 0 }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">校验</span>
              <el-tag
                v-if="proposal.validation_results"
                :type="proposal.validation_results.passed ? 'success' : 'warning'"
                size="small"
              >
                {{ proposal.validation_results.passed ? '通过' : '未通过' }}
              </el-tag>
              <span v-else>-</span>
            </div>
          </div>
        </div>
        <!-- 失败原因 -->
        <el-alert
          v-if="proposal.status === 'failed' && proposal.error_message"
          type="error"
          :closable="false"
          show-icon
          class="mt-12"
        >
          <template #title>生成失败:{{ proposal.error_message }}</template>
        </el-alert>
        <!-- LLM 降级提示 -->
        <el-alert
          v-if="proposal.llm_error"
          type="warning"
          :closable="false"
          show-icon
          class="mt-12"
        >
          <template #title>
            LLM 不可用({{ proposal.llm_error_type || 'unknown' }}),Agent 已降级为规则模板模式
          </template>
          <div>{{ proposal.llm_error }}</div>
        </el-alert>
      </el-card>

      <!-- 生成元信息 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Document /></el-icon>
            <span>生成信息</span>
          </div>
        </template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="生成编号">{{ proposal.proposal_no }}</el-descriptions-item>
          <el-descriptions-item label="招标文件">
            <el-link v-if="proposal.bid" type="primary" :underline="false" @click="goBid">
              {{ proposal.bid.title }}
            </el-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="文件名">
            {{ proposal.file_info?.name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatTime(proposal.started_time) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatTime(proposal.finished_time) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(proposal.created_time) }}</el-descriptions-item>
          <el-descriptions-item label="文件大小" :span="3">
            {{ proposal.file_info ? formatFileSize(proposal.file_info.size) : '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- AI 生成章节 -->
      <el-card v-if="proposal.generated_sections?.length" class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><MagicStick /></el-icon>
            <span>AI 生成章节</span>
            <el-tag size="small" type="info" class="header-tag">
              {{ proposal.generated_sections.length }} 章节
            </el-tag>
          </div>
        </template>
        <el-collapse>
          <el-collapse-item
            v-for="(s, idx) in proposal.generated_sections"
            :key="idx"
            :name="idx"
          >
            <template #title>
              <span class="section-title">
                {{ s.section_name || s.section_type }}
                <el-tag size="small" :type="s.source === 'ai' ? 'primary' : 'success'" class="ml-8">
                  {{ s.source === 'ai' ? 'AI 生成' : '规则模板' }}
                </el-tag>
              </span>
            </template>
            <div class="section-content">{{ s.content }}</div>
            <div v-if="s.references?.length" class="section-refs">
              <strong>参考来源:</strong>
              <ul>
                <li v-for="(r, ri) in s.references" :key="ri">
                  <el-tag size="small" type="info">{{ r.document_title || '未知文档' }}</el-tag>
                  <span v-if="r.page_number"> 第 {{ r.page_number }} 页</span>
                  <span v-if="r.score"> 相似度 {{ (r.score * 100).toFixed(1) }}%</span>
                  <span v-if="r.chunk_id"> 片段#{{ r.chunk_id }}</span>
                </li>
              </ul>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>

      <!-- RAG 命中规范 -->
      <el-card v-if="proposal.rag_references?.length" class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Collection /></el-icon>
            <span>RAG 命中规范</span>
            <el-tag size="small" type="info" class="header-tag">
              {{ proposal.rag_references.length }} 条
            </el-tag>
          </div>
        </template>
        <el-table :data="proposal.rag_references" stripe border>
          <el-table-column label="文档" prop="document_title" min-width="180" show-overflow-tooltip />
          <el-table-column label="页码" prop="page_number" width="80" align="center" />
          <el-table-column label="片段" prop="chunk_id" width="80" align="center" />
          <el-table-column label="相似度" width="110">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round((row.score || 0) * 100)"
                :stroke-width="10"
                :status="(row.score || 0) >= 0.6 ? 'success' : ''"
              />
            </template>
          </el-table-column>
          <el-table-column label="文本片段" prop="text" min-width="300" show-overflow-tooltip />
        </el-table>
      </el-card>

      <!-- 校验结果 -->
      <el-card
        v-if="proposal.validation_results && !proposal.validation_results.passed"
        class="mb-16"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <el-icon><Warning /></el-icon>
            <span>校验问题</span>
            <el-tag size="small" type="warning" class="header-tag">
              {{ proposal.validation_results.issues?.length || 0 }} 项
            </el-tag>
          </div>
        </template>
        <el-table :data="proposal.validation_results.issues" stripe border>
          <el-table-column label="类型" prop="type" width="180" />
          <el-table-column label="严重度" width="100">
            <template #default="{ row }">
              <el-tag :type="row.severity === 'high' ? 'danger' : 'warning'" size="small">
                {{ row.severity === 'high' ? '高' : '中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="问题描述" prop="description" min-width="200" show-overflow-tooltip />
          <el-table-column label="建议" prop="suggestion" min-width="200" show-overflow-tooltip />
        </el-table>
      </el-card>

      <!-- Agent 执行过程 Trace -->
      <el-card
        v-if="proposal.agent_trace && proposal.agent_trace.length > 0"
        class="mb-16 agent-trace-card"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <el-icon><Cpu /></el-icon>
            <span>Agent 执行过程</span>
            <el-tag size="small" type="info" class="header-tag">
              {{ proposal.agent_trace.length }} 步 · {{ proposal.iterations ?? 0 }} 次迭代
            </el-tag>
          </div>
        </template>

        <!-- Trace 汇总统计 -->
        <div v-if="proposal.trace_summary" class="trace-summary-bar">
          <div class="trace-stat-item">
            <span class="trace-stat-label">总步数</span>
            <span class="trace-stat-value">{{ proposal.trace_summary.steps ?? proposal.agent_trace.length }}</span>
          </div>
          <div class="trace-stat-item">
            <span class="trace-stat-label">总耗时</span>
            <span class="trace-stat-value">{{ proposal.trace_summary.total_duration_ms ?? 0 }} ms</span>
          </div>
          <div class="trace-stat-item">
            <span class="trace-stat-label">LLM 耗时</span>
            <span class="trace-stat-value primary">{{ proposal.trace_summary.llm_duration_ms ?? 0 }} ms</span>
          </div>
          <div class="trace-stat-item">
            <span class="trace-stat-label">Tool 耗时</span>
            <span class="trace-stat-value success">{{ proposal.trace_summary.tool_duration_ms ?? 0 }} ms</span>
          </div>
        </div>

        <!-- Agent Timeline -->
        <el-timeline class="agent-timeline">
          <el-timeline-item
            v-for="step in proposal.agent_trace"
            :key="step.step"
            :type="traceStepType(step.status)"
            :hollow="step.status === 'skipped'"
            placement="top"
          >
            <div class="trace-step">
              <div class="trace-step-header">
                <span class="trace-step-num">#{{ step.step }}</span>
                <el-tag size="small" :type="traceActionTagType(step.action)">
                  {{ traceActionLabel(step.action) }}
                </el-tag>
                <span v-if="step.tool_name" class="trace-tool-name">
                  🔧 {{ step.tool_name }}
                </span>
                <span class="trace-duration">⏱ {{ step.duration_ms ?? 0 }} ms</span>
                <el-tag
                  size="small"
                  :type="traceStatusTagType(step.status)"
                  effect="plain"
                  class="trace-status-tag"
                >
                  {{ traceStatusLabel(step.status) }}
                </el-tag>
              </div>

              <div v-if="step.thought" class="trace-line trace-thought">
                <span class="trace-emoji">🧠</span>
                <span class="trace-field-label">Thought</span>
                <span class="trace-field-text">{{ step.thought }}</span>
              </div>
              <div v-if="step.decision" class="trace-line trace-decision">
                <span class="trace-emoji">📌</span>
                <span class="trace-field-label">Decision</span>
                <span class="trace-field-text">{{ step.decision }}</span>
              </div>
              <div v-if="formatToolInput(step.tool_input)" class="trace-line trace-input">
                <span class="trace-emoji">📥</span>
                <span class="trace-field-label">Input</span>
                <code class="trace-code-inline">{{ formatToolInput(step.tool_input) }}</code>
              </div>
              <div v-if="formatObservation(step.observation)" class="trace-line trace-observation">
                <span class="trace-emoji">📄</span>
                <span class="trace-field-label">Observation</span>
                <pre class="trace-code-block">{{ formatObservation(step.observation) }}</pre>
              </div>
              <div v-if="step.error_message" class="trace-line trace-error">
                <span class="trace-emoji">❌</span>
                <span class="trace-field-label">Error</span>
                <span class="trace-field-text text-danger">{{ step.error_message }}</span>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <!-- Agent 工具调用统计 -->
      <el-card v-if="proposal.trace_summary?.tool_stats" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Monitor /></el-icon>
            <span>工具调用统计</span>
          </div>
        </template>
        <el-table :data="toolStatsList" stripe border>
          <el-table-column label="工具名" prop="name" min-width="180" />
          <el-table-column label="调用次数" prop="call_count" width="100" align="center" />
          <el-table-column label="成功" prop="success_count" width="80" align="center" />
          <el-table-column label="失败" prop="failed_count" width="80" align="center" />
          <el-table-column label="总耗时" width="120">
            <template #default="{ row }">{{ row.total_ms }} ms</template>
          </el-table-column>
          <el-table-column label="最近错误" prop="last_error" min-width="200" show-overflow-tooltip />
        </el-table>
      </el-card>
    </template>

    <el-empty v-else-if="!loading" description="生成记录不存在或加载失败" />
  </div>
</template>

<script setup>
/**
 * 投标生成详情页(Sprint 7 - v0.9.0)
 *
 * 展示内容:
 * 1. 生成状态总览(status / 章节数 / RAG 命中数 / 迭代次数 / 校验结果)
 * 2. 生成元信息(生成编号 / 招标文件 / 时间 / 文件大小)
 * 3. AI 生成章节(可折叠,含 RAG 引用来源)
 * 4. RAG 命中规范(文档 / 页码 / 相似度)
 * 5. 校验问题(若校验未通过)
 * 6. Agent 执行过程 Trace(Timeline:Thought → Decision → Action → Observation)
 * 7. 工具调用统计
 * 8. 下载 Word 文档
 *
 * 镜像 Sprint 6 GenerationDetail.vue 的 Trace Timeline 模式
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Back, Document, MagicStick, Collection, Warning, Cpu, Monitor, Download,
} from '@element-plus/icons-vue'
import { getProposalDetail, downloadProposal } from '@/api/bid'
import {
  PROPOSAL_STATUS_LABELS, PROPOSAL_STATUS_TAG_TYPES,
} from '@/utils/constants'
import { formatTime, formatFileSize } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const proposal = ref(null)

const overviewCardClass = computed(() => {
  const s = proposal.value?.status
  if (s === 'success') return 'overview-success'
  if (s === 'failed') return 'overview-failed'
  if (s === 'running') return 'overview-running'
  return ''
})

const toolStatsList = computed(() => {
  const stats = proposal.value?.trace_summary?.tool_stats
  if (!stats || typeof stats !== 'object') return []
  return Object.entries(stats).map(([name, s]) => ({
    name,
    call_count: s.call_count ?? 0,
    success_count: s.success_count ?? 0,
    failed_count: s.failed_count ?? 0,
    total_ms: s.total_ms ?? 0,
    last_error: s.last_error || '',
  }))
})

async function fetchDetail() {
  loading.value = true
  try {
    const res = await getProposalDetail(route.params.id)
    proposal.value = res.data.proposal
  } catch (e) {
    // 错误提示由拦截器统一处理
  } finally {
    loading.value = false
  }
}

async function handleDownload() {
  if (!proposal.value) return
  try {
    const res = await downloadProposal(proposal.value.id)
    const url = window.URL.createObjectURL(res)
    const a = document.createElement('a')
    a.href = url
    a.download = proposal.value.file_info?.name
      ? proposal.value.file_info.name
      : `${proposal.value.proposal_no}.docx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('文件下载已开始')
  } catch (e) {
    // 错误提示由拦截器统一处理
  }
}

function goBid() {
  if (proposal.value?.bid_document_id) {
    router.push(`/bids/${proposal.value.bid_document_id}`)
  }
}

// ---------- Agent Trace 辅助函数(复用 Sprint 6 GenerationDetail 模式) ----------
const TRACE_ACTION_LABELS = {
  llm_call: 'LLM 决策',
  call_tool: '调用工具',
  final_report: '生成报告',
  system: '系统处理',
  iteration_exceeded: '迭代超限',
  fallback: '降级规则模板',
}
const TRACE_ACTION_TAG_TYPES = {
  llm_call: 'primary',
  call_tool: 'success',
  final_report: 'warning',
  system: 'info',
  iteration_exceeded: 'danger',
  fallback: 'danger',
}
const TRACE_STATUS_LABELS = {
  success: '✅ 成功',
  failed: '❌ 失败',
  skipped: '⏭ 跳过',
}
const TRACE_STATUS_TAG_TYPES = {
  success: 'success',
  failed: 'danger',
  skipped: 'info',
}

function traceActionLabel(action) {
  return TRACE_ACTION_LABELS[action] || action || '-'
}
function traceActionTagType(action) {
  return TRACE_ACTION_TAG_TYPES[action] || 'info'
}
function traceStatusLabel(status) {
  return TRACE_STATUS_LABELS[status] || status || '-'
}
function traceStatusTagType(status) {
  return TRACE_STATUS_TAG_TYPES[status] || 'info'
}
function traceStepType(status) {
  return TRACE_STATUS_TAG_TYPES[status] || 'primary'
}

function formatToolInput(input) {
  if (!input) return ''
  if (typeof input === 'string') return input
  if (typeof input === 'object') {
    const keys = Object.keys(input)
    if (keys.length === 0) return ''
    return JSON.stringify(input)
  }
  return String(input)
}

function formatObservation(obs) {
  if (obs === null || obs === undefined || obs === '') return ''
  if (typeof obs === 'string') return obs
  try {
    return JSON.stringify(obs, null, 2)
  } catch (e) {
    return String(obs)
  }
}

import { onMounted } from 'vue'
onMounted(() => {
  fetchDetail()
})
</script>

<style scoped>
.page-container { padding: 0; }
.mb-16 { margin-bottom: 16px; }
.mt-12 { margin-top: 12px; }
.ml-8 { margin-left: 8px; }
.action-card { border: 1px solid #ebeef5; }
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.action-right {
  display: flex;
  gap: 8px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-tag {
  margin-left: auto;
}

/* 状态总览卡片 */
.status-overview {
  border-left: 4px solid #409eff;
}
.overview-success {
  border-left-color: #67c23a;
  background: linear-gradient(90deg, rgba(103,194,58,0.05) 0%, transparent 100%);
}
.overview-failed {
  border-left-color: #f56c6c;
  background: linear-gradient(90deg, rgba(245,108,108,0.05) 0%, transparent 100%);
}
.overview-running {
  border-left-color: #e6a23c;
  background: linear-gradient(90deg, rgba(230,162,60,0.05) 0%, transparent 100%);
}
.overview-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.overview-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.overview-label {
  font-size: 13px;
  color: #909399;
}
.overview-right {
  display: flex;
  gap: 32px;
}
.overview-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}
.stat-value.info { color: #409eff; }
.stat-value.danger { color: #f56c6c; }
.stat-value.warning { color: #e6a23c; }
.stat-value.success { color: #67c23a; }

/* AI 章节 */
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-content {
  white-space: pre-wrap;
  line-height: 1.8;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}
.section-refs {
  margin-top: 12px;
  font-size: 13px;
  color: #606266;
}
.section-refs ul {
  margin: 6px 0 0 18px;
  padding: 0;
}
.section-refs li {
  margin: 4px 0;
}

/* Trace Timeline */
.trace-summary-bar {
  display: flex;
  gap: 32px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.trace-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.trace-stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.trace-stat-value {
  font-size: 18px;
  font-weight: 600;
}
.trace-stat-value.primary { color: #409eff; }
.trace-stat-value.success { color: #67c23a; }

.trace-step {
  padding: 8px 0;
}
.trace-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.trace-step-num {
  font-weight: 600;
  color: #303133;
}
.trace-tool-name {
  font-family: monospace;
  color: #409eff;
  font-size: 13px;
}
.trace-duration {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}
.trace-status-tag {
  margin-left: 8px;
}
.trace-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.6;
}
.trace-emoji {
  flex-shrink: 0;
}
.trace-field-label {
  flex-shrink: 0;
  font-weight: 600;
  color: #606266;
  min-width: 80px;
}
.trace-field-text {
  color: #303133;
}
.trace-code-inline {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
  color: #c7254e;
}
.trace-code-block {
  background: #f5f7fa;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #303133;
  max-height: 240px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  flex: 1;
}
.trace-error .trace-field-text {
  color: #f56c6c;
}

.text-muted { color: #909399; font-size: 12px; }
.text-danger { color: #f56c6c; }
</style>
