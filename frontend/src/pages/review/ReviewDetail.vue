<template>
  <!-- 审核报告详情页:风险等级 / 风险列表 / 依据 / 来源文档 / 修改建议 / Agent 轨迹 -->
  <div class="page-container" v-loading="loading">
    <!-- 顶部操作栏 -->
    <el-card class="action-card mb-16" shadow="never">
      <div class="action-bar">
        <el-button :icon="Back" @click="router.back()">返回</el-button>
        <div class="action-right">
          <el-button :icon="Document" @click="goContract">查看合同</el-button>
        </div>
      </div>
    </el-card>

    <template v-if="review">
      <!-- 风险等级总览卡片 -->
      <el-card class="risk-overview-card mb-16" shadow="never" :class="overviewCardClass">
        <div class="overview-content">
          <div class="overview-left">
            <div class="overview-label">总体风险等级</div>
            <div class="overview-level">
              <el-tag
                v-if="review.risk_level"
                :type="RISK_LEVEL_TAG_TYPES[review.risk_level] || 'info'"
                effect="dark"
                size="large"
              >
                {{ RISK_LEVEL_LABELS[review.risk_level] || review.risk_level }}
              </el-tag>
              <el-tag v-else type="info" effect="plain" size="large">
                未评估
              </el-tag>
            </div>
          </div>
          <div class="overview-right">
            <div class="overview-stat">
              <span class="stat-label">风险数</span>
              <span class="stat-value">{{ riskCount }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">高风险</span>
              <span class="stat-value danger">{{ highRiskCount }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">中风险</span>
              <span class="stat-value warning">{{ mediumRiskCount }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">低风险</span>
              <span class="stat-value info">{{ lowRiskCount }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">状态</span>
              <el-tag :type="REVIEW_STATUS_TAG_TYPES[review.status] || 'info'" size="small">
                {{ REVIEW_STATUS_LABELS[review.status] || review.status }}
              </el-tag>
            </div>
          </div>
        </div>
        <!-- 审核总结 -->
        <div v-if="review.summary" class="overview-summary">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ review.summary }}</span>
        </div>
        <!-- 失败原因 -->
        <el-alert
          v-if="review.status === 'failed' && review.error_message"
          type="error"
          :closable="false"
          show-icon
          class="mt-12"
        >
          <template #title>审核失败:{{ review.error_message }}</template>
        </el-alert>
      </el-card>

      <!-- 审核元信息 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Document /></el-icon>
            <span>审核信息</span>
          </div>
        </template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="审核编号">
            {{ review.review_no }}
          </el-descriptions-item>
          <el-descriptions-item label="关联合同">
            <el-link
              v-if="review.contract_id"
              type="primary"
              :underline="false"
              @click="goContract"
            >
              合同 #{{ review.contract_id }}
            </el-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="关联分析任务">
            <span v-if="review.task_id">任务 #{{ review.task_id }}</span>
            <span v-else class="text-muted">无(降级旧数据)</span>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ formatTime(review.started_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="完成时间">
            {{ formatTime(review.finished_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="Agent 迭代次数">
            {{ review.iterations ?? 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatTime(review.created_time) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="review.llm_error" label="LLM 异常" :span="2">
            <span class="text-danger">{{ review.llm_error }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 风险详情列表 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Warning /></el-icon>
            <span>风险详情</span>
            <el-tag v-if="riskCount > 0" size="small" type="danger" class="header-tag">
              共 {{ riskCount }} 项
            </el-tag>
          </div>
        </template>

        <!-- 风险卡片列表(按严重度降序) -->
        <div v-if="sortedRisks.length > 0" class="risk-list">
          <div
            v-for="(risk, idx) in sortedRisks"
            :key="idx"
            class="risk-card"
            :class="`risk-sev-${risk.severity}`"
          >
            <!-- 风险头部 -->
            <div class="risk-header">
              <div class="risk-title">
                <el-tag
                  :type="RISK_SEVERITY_TAG_TYPES[risk.severity] || 'info'"
                  size="small"
                  effect="dark"
                >
                  {{ RISK_SEVERITY_LABELS[risk.severity] || risk.severity }}
                </el-tag>
                <span class="risk-type">{{ risk.type || '其他' }}</span>
                <span class="risk-index">#{{ idx + 1 }}</span>
              </div>
            </div>

            <!-- 风险描述 -->
            <div class="risk-desc">{{ risk.description || '无描述' }}</div>

            <!-- 风险依据 -->
            <div v-if="risk.evidence" class="risk-section">
              <div class="section-label">
                <el-icon><Tickets /></el-icon>
                <span>风险依据</span>
              </div>
              <div class="section-content evidence">{{ risk.evidence }}</div>
            </div>

            <!-- 修改建议 -->
            <div v-if="risk.suggestion" class="risk-section">
              <div class="section-label">
                <el-icon><EditPen /></el-icon>
                <span>修改建议</span>
              </div>
              <div class="section-content suggestion">{{ risk.suggestion }}</div>
            </div>

            <!-- 来源文档(RAG 引用) -->
            <div v-if="risk.references && risk.references.length > 0" class="risk-section">
              <div class="section-label">
                <el-icon><Link /></el-icon>
                <span>来源文档({{ risk.references.length }})</span>
              </div>
              <div class="references-list">
                <div
                  v-for="(ref, rIdx) in risk.references"
                  :key="rIdx"
                  class="reference-item"
                >
                  <el-tag size="small" type="info" class="ref-doc">
                    {{ ref.document_title || '未知文档' }}
                  </el-tag>
                  <span class="ref-meta">
                    <span v-if="ref.page_number !== null && ref.page_number !== undefined">
                      第 {{ ref.page_number }} 页
                    </span>
                    <span v-if="ref.score !== null && ref.score !== undefined" class="ref-score">
                      相似度 {{ formatScore(ref.score) }}
                    </span>
                    <span v-if="ref.chunk_id !== null && ref.chunk_id !== undefined" class="ref-chunk">
                      片段#{{ ref.chunk_id }}
                    </span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 无风险占位 -->
        <el-empty
          v-else-if="review.status === 'success'"
          description="未发现风险,合同条款合规"
        />
        <el-empty
          v-else
          description="审核未成功完成,无风险详情"
        />
      </el-card>

      <!-- Agent 执行过程 Trace(v0.7.1 新增:Thought → Decision → Action → Observation → Duration → Status) -->
      <el-card
        v-if="review.agent_trace && review.agent_trace.length > 0"
        class="mb-16 agent-trace-card"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <el-icon><Cpu /></el-icon>
            <span>Agent 执行过程</span>
            <el-tag size="small" type="info" class="header-tag">
              {{ review.agent_trace.length }} 步 · {{ review.iterations ?? 0 }} 次迭代
            </el-tag>
          </div>
        </template>

        <!-- Trace 汇总统计条 -->
        <div v-if="review.trace_summary" class="trace-summary-bar">
          <div class="trace-stat-item">
            <span class="trace-stat-label">总步数</span>
            <span class="trace-stat-value">{{ review.trace_summary.steps ?? review.agent_trace.length }}</span>
          </div>
          <div class="trace-stat-item">
            <span class="trace-stat-label">总耗时</span>
            <span class="trace-stat-value">{{ review.trace_summary.total_duration_ms ?? 0 }} ms</span>
          </div>
          <div class="trace-stat-item">
            <span class="trace-stat-label">LLM 耗时</span>
            <span class="trace-stat-value primary">{{ review.trace_summary.llm_duration_ms ?? 0 }} ms</span>
          </div>
          <div class="trace-stat-item">
            <span class="trace-stat-label">Tool 耗时</span>
            <span class="trace-stat-value success">{{ review.trace_summary.tool_duration_ms ?? 0 }} ms</span>
          </div>
        </div>

        <!-- LLM 降级提示 -->
        <el-alert
          v-if="review.llm_error_type"
          :type="review.llm_error_type === 'auth' ? 'error' : 'warning'"
          :closable="false"
          show-icon
          class="mb-12"
        >
          <template #title>
            本次审核采用规则引擎降级模式({{ review.llm_error_type }})
          </template>
          <template v-if="review.llm_error" #default>
            <span class="text-danger">{{ review.llm_error }}</span>
          </template>
        </el-alert>

        <!-- Agent 执行 Timeline -->
        <el-timeline class="agent-timeline">
          <el-timeline-item
            v-for="step in review.agent_trace"
            :key="step.step"
            :type="traceStepType(step.status)"
            :hollow="step.status === 'skipped'"
            placement="top"
          >
            <div class="trace-step">
              <!-- Step 头部:序号 + Action 标签 + 工具名 + 耗时 + 状态 -->
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

              <!-- Thought -->
              <div v-if="step.thought" class="trace-line trace-thought">
                <span class="trace-emoji">🧠</span>
                <span class="trace-field-label">Thought</span>
                <span class="trace-field-text">{{ step.thought }}</span>
              </div>

              <!-- Decision -->
              <div v-if="step.decision" class="trace-line trace-decision">
                <span class="trace-emoji">📌</span>
                <span class="trace-field-label">Decision</span>
                <span class="trace-field-text">{{ step.decision }}</span>
              </div>

              <!-- Tool Input -->
              <div v-if="formatToolInput(step.tool_input)" class="trace-line trace-input">
                <span class="trace-emoji">📥</span>
                <span class="trace-field-label">Input</span>
                <code class="trace-code-inline">{{ formatToolInput(step.tool_input) }}</code>
              </div>

              <!-- Observation -->
              <div
                v-if="formatObservation(step.observation)"
                class="trace-line trace-observation"
              >
                <span class="trace-emoji">📄</span>
                <span class="trace-field-label">Observation</span>
                <pre class="trace-code-block">{{ formatObservation(step.observation) }}</pre>
              </div>

              <!-- Error -->
              <div v-if="step.error_message" class="trace-line trace-error">
                <span class="trace-emoji">❌</span>
                <span class="trace-field-label">Error</span>
                <span class="trace-field-text text-danger">{{ step.error_message }}</span>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <!-- Agent 工具调用轨迹(审计用,折叠展示) -->
      <el-card v-if="review.tool_calls_log && review.tool_calls_log.length > 0" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Monitor /></el-icon>
            <span>Agent 工具调用轨迹</span>
            <el-tag size="small" type="info" class="header-tag">
              {{ review.tool_calls_log.length }} 次调用
            </el-tag>
          </div>
        </template>
        <el-timeline>
          <el-timeline-item
            v-for="(call, idx) in review.tool_calls_log"
            :key="idx"
            :type="call.error ? 'danger' : 'success'"
            :timestamp="`${call.duration_ms ?? 0} ms`"
            placement="top"
          >
            <div class="tool-call">
              <div class="tool-call-header">
                <el-tag size="small" :type="call.error ? 'danger' : 'primary'">
                  {{ call.tool || '未知工具' }}
                </el-tag>
                <span v-if="call.error" class="tool-error">{{ call.error }}</span>
              </div>
              <div v-if="call.result_summary" class="tool-summary">
                {{ call.result_summary }}
              </div>
              <div v-if="call.args && Object.keys(call.args).length > 0" class="tool-args">
                参数:{{ JSON.stringify(call.args) }}
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </template>

    <!-- 加载中占位 -->
    <el-empty v-else-if="!loading" description="审核报告不存在或加载失败" />
  </div>
</template>

<script setup>
/**
 * 审核报告详情页(Sprint 5 - v0.7.0)
 *
 * 展示内容(对应任务书 5 项):
 * 1. 总体风险等级 — 顶部风险等级卡片(high=红/medium=橙/low=蓝/none=绿)
 * 2. 风险列表 — 风险卡片列表(按 severity 降序)
 * 3. 风险依据 — 每个风险卡片的"依据"区块(risk.evidence)
 * 4. 来源文档 — 每个风险卡片的"来源"区块(risk.references:document_title/page_number/score)
 * 5. 修改建议 — 每个风险卡片的"建议"区块(risk.suggestion)
 *
 * 额外展示:
 * - 审核元信息(review_no / status / started_time / finished_time / iterations)
 * - Agent 工具调用轨迹(tool_calls_log,时间线展示,审计用)
 * - 审核总结(review.summary)
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Back, Document, Warning, InfoFilled, Tickets, EditPen, Link, Monitor, Cpu,
} from '@element-plus/icons-vue'
import { getReviewDetail } from '@/api/review'
import {
  REVIEW_STATUS_LABELS,
  REVIEW_STATUS_TAG_TYPES,
  RISK_LEVEL_LABELS,
  RISK_LEVEL_TAG_TYPES,
  RISK_SEVERITY_LABELS,
  RISK_SEVERITY_TAG_TYPES,
  RISK_SEVERITY_ORDER,
} from '@/utils/constants'
import { formatTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const review = ref(null)

// ---------- 风险列表(按严重度降序) ----------
const sortedRisks = computed(() => {
  const risks = review.value?.risks
  if (!Array.isArray(risks)) return []
  return [...risks].sort((a, b) => {
    const sa = RISK_SEVERITY_ORDER[a.severity] || 0
    const sb = RISK_SEVERITY_ORDER[b.severity] || 0
    return sb - sa
  })
})

const riskCount = computed(() => sortedRisks.value.length)
const highRiskCount = computed(
  () => sortedRisks.value.filter((r) => r.severity === 'high').length
)
const mediumRiskCount = computed(
  () => sortedRisks.value.filter((r) => r.severity === 'medium').length
)
const lowRiskCount = computed(
  () => sortedRisks.value.filter((r) => r.severity === 'low').length
)

// ---------- 总览卡片样式(根据风险等级) ----------
const overviewCardClass = computed(() => {
  const level = review.value?.risk_level
  if (level === 'high') return 'overview-high'
  if (level === 'medium') return 'overview-medium'
  if (level === 'low') return 'overview-low'
  if (level === 'none') return 'overview-none'
  return ''
})

// ---------- 工具函数 ----------
function formatScore(score) {
  if (score === null || score === undefined) return '-'
  return (Math.round(score * 100) / 100).toFixed(2)
}

function goContract() {
  if (review.value?.contract_id) {
    router.push(`/contracts/${review.value.contract_id}`)
  }
}

// ---------- Agent Trace 辅助函数(v0.7.1 新增) ----------
// Thought → Decision → Action → Observation → Duration → Status
const TRACE_ACTION_LABELS = {
  llm_call: 'LLM 决策',
  call_tool: '调用工具',
  final_report: '生成报告',
  system: '系统处理',
  iteration_exceeded: '迭代超限',
  fallback: '降级规则引擎',
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
  // el-timeline-item type: primary / success / warning / danger / info
  return TRACE_STATUS_TAG_TYPES[status] || 'primary'
}

function formatObservation(obs) {
  if (obs === null || obs === undefined || obs === '') return ''
  if (typeof obs === 'string') {
    return obs.length > 500 ? obs.substring(0, 500) + '\n...(已截断)' : obs
  }
  try {
    const str = JSON.stringify(obs, null, 2)
    return str.length > 500 ? str.substring(0, 500) + '\n...(已截断)' : str
  } catch {
    return String(obs)
  }
}

function formatToolInput(input) {
  if (!input || (typeof input === 'object' && Object.keys(input).length === 0)) return ''
  try {
    const str = JSON.stringify(input)
    return str.length > 300 ? str.substring(0, 300) + '...' : str
  } catch {
    return String(input)
  }
}

// ---------- 加载审核详情 ----------
async function loadDetail() {
  loading.value = true
  try {
    const id = route.params.id
    const res = await getReviewDetail(id)
    review.value = res.data.review
  } catch (err) {
    review.value = null
  } finally {
    loading.value = false
  }
}

loadDetail()
</script>

<style scoped>
.action-card {
  background-color: #fff;
}

.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.action-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.header-tag {
  margin-left: auto;
}

.mb-16 {
  margin-bottom: 16px;
}

.mt-12 {
  margin-top: 12px;
}

.text-muted {
  color: #c0c4cc;
}

.text-danger {
  color: #f56c6c;
}

/* ---------- 风险等级总览 ---------- */
.risk-overview-card {
  border-left: 4px solid #909399;
}

.overview-high {
  border-left-color: #f56c6c;
  background-color: #fef0f0;
}

.overview-medium {
  border-left-color: #e6a23c;
  background-color: #fdf6ec;
}

.overview-low {
  border-left-color: #409eff;
  background-color: #ecf5ff;
}

.overview-none {
  border-left-color: #67c23a;
  background-color: #f0f9eb;
}

.overview-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
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
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.overview-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}

.stat-value.danger {
  color: #f56c6c;
}

.stat-value.warning {
  color: #e6a23c;
}

.stat-value.info {
  color: #409eff;
}

.overview-summary {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #dcdfe6;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
}

.overview-summary .el-icon {
  color: #909399;
  margin-top: 2px;
  flex-shrink: 0;
}

/* ---------- 风险卡片 ---------- */
.risk-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.risk-card {
  border: 1px solid #ebeef5;
  border-left: 4px solid #909399;
  border-radius: 4px;
  padding: 16px;
  background-color: #fafafa;
}

.risk-sev-high {
  border-left-color: #f56c6c;
  background-color: #fef0f0;
}

.risk-sev-medium {
  border-left-color: #e6a23c;
  background-color: #fdf6ec;
}

.risk-sev-low {
  border-left-color: #409eff;
  background-color: #ecf5ff;
}

.risk-header {
  margin-bottom: 8px;
}

.risk-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.risk-type {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.risk-index {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}

.risk-desc {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 12px;
}

.risk-section {
  margin-top: 10px;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 4px;
}

.section-label .el-icon {
  color: #909399;
}

.section-content {
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 12px;
  border-radius: 4px;
}

.section-content.evidence {
  background-color: #fff;
  border: 1px solid #ebeef5;
  color: #606266;
}

.section-content.suggestion {
  background-color: #f0f9eb;
  border: 1px solid #e1f3d8;
  color: #529b2e;
}

/* ---------- 来源文档 ---------- */
.references-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.reference-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background-color: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  flex-wrap: wrap;
}

.ref-doc {
  flex-shrink: 0;
}

.ref-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #909399;
  flex-wrap: wrap;
}

.ref-score {
  color: #67c23a;
  font-weight: 500;
}

.ref-chunk {
  font-family: monospace;
}

/* ---------- Agent 工具调用轨迹 ---------- */
.tool-call {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-error {
  font-size: 12px;
  color: #f56c6c;
}

.tool-summary {
  font-size: 13px;
  color: #606266;
}

.tool-args {
  font-size: 12px;
  color: #909399;
  font-family: monospace;
  word-break: break-all;
}

/* ---------- Agent 执行过程 Trace(v0.7.1 新增) ---------- */
.agent-trace-card {
  border-left: 4px solid #6366f1;
}

.trace-summary-bar {
  display: flex;
  align-items: center;
  gap: 32px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background-color: #f5f7fa;
  border-radius: 4px;
  flex-wrap: wrap;
}

.trace-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.trace-stat-label {
  font-size: 12px;
  color: #909399;
}

.trace-stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}

.trace-stat-value.primary {
  color: #409eff;
}

.trace-stat-value.success {
  color: #67c23a;
}

.agent-timeline {
  padding-left: 8px;
}

.trace-step {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.trace-step-num {
  font-size: 13px;
  font-weight: 700;
  color: #6366f1;
  font-family: monospace;
}

.trace-tool-name {
  font-size: 13px;
  color: #67c23a;
  font-weight: 500;
}

.trace-duration {
  font-size: 12px;
  color: #909399;
  margin-left: auto;
  font-family: monospace;
}

.trace-status-tag {
  margin-left: 0;
}

.trace-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
  padding: 4px 0;
}

.trace-emoji {
  flex-shrink: 0;
  font-size: 14px;
  line-height: 1.6;
}

.trace-field-label {
  flex-shrink: 0;
  font-weight: 600;
  color: #606266;
  min-width: 72px;
}

.trace-field-text {
  color: #303133;
  word-break: break-word;
}

.trace-thought {
  background-color: #f0f5ff;
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 2px solid #409eff;
}

.trace-thought .trace-field-label {
  color: #409eff;
}

.trace-decision {
  background-color: #fdf6ec;
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 2px solid #e6a23c;
}

.trace-decision .trace-field-label {
  color: #e6a23c;
}

.trace-input {
  background-color: #f5f7fa;
  padding: 4px 10px;
  border-radius: 4px;
}

.trace-observation {
  background-color: #f0f9eb;
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 2px solid #67c23a;
  flex-direction: column;
}

.trace-observation .trace-field-label {
  color: #67c23a;
  margin-bottom: 4px;
}

.trace-error {
  background-color: #fef0f0;
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 2px solid #f56c6c;
}

.trace-error .trace-field-label {
  color: #f56c6c;
}

.trace-code-inline {
  font-size: 12px;
  color: #606266;
  background-color: #fff;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #ebeef5;
  font-family: 'Consolas', 'Monaco', monospace;
  word-break: break-all;
}

.trace-code-block {
  margin: 0;
  width: 100%;
  font-size: 12px;
  color: #606266;
  background-color: #fff;
  padding: 8px 12px;
  border-radius: 4px;
  border: 1px solid #ebeef5;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
}
</style>
