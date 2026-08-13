<template>
  <!-- AI 评估(Sprint 8.5 - v1.0.0 封版前 AI 质量评估,信息架构重构后归入系统管理) -->
  <div class="page-container">
    <!-- 顶部操作栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <div class="overview-header">
        <div class="overview-title">
          <el-icon class="title-icon"><DataLine /></el-icon>
          <div>
            <h2 class="title-text">AI 评估</h2>
            <p class="title-desc">
              RAG 知识库检索质量 + AI 调用稳定性 + Agent 工具调用统计,封版前 AI 质量验收
            </p>
          </div>
        </div>
        <div class="overview-actions">
          <el-tag
            v-if="summary && summary.status"
            :type="statusTagType(summary.status)"
            effect="dark"
            size="large"
          >
            {{ summary.status }} · {{ summary.status_label || '' }}
          </el-tag>
          <!-- Sprint 8.6.1: 评估模式选择(执行中禁用) -->
          <el-radio-group v-model="evalMode" :disabled="taskActive" size="default">
            <el-radio-button v-for="m in evalModes" :key="m.value" :value="m.value">
              {{ m.label }}
            </el-radio-button>
          </el-radio-group>
          <el-tooltip :content="evalModeTip" placement="top" :disabled="taskActive">
            <el-button :icon="Refresh" @click="loadSummary" :disabled="taskActive">刷新</el-button>
          </el-tooltip>
          <el-button
            type="primary"
            :icon="VideoPlay"
            :loading="runLoading"
            :disabled="runLoading || taskActive"
            @click="handleRunEvaluation"
          >
            {{ runLoading ? 'AI 评估执行中…' : '执行评估' }}
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- Sprint 8.6.1: 异步任务实时进度 -->
    <el-card v-if="taskActive || taskFinished" class="mb-16 eval-task-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>评估执行任务</span>
          <el-tag :type="taskTagType" size="small" effect="dark">{{ taskStatusLabel }}</el-tag>
        </div>
      </template>
      <el-progress
        :percentage="taskProgress"
        :status="taskStatus === 'failed' ? 'exception' : taskStatus === 'success' ? 'success' : undefined"
        :stroke-width="16"
        striped
        :striped-flow="taskStatus === 'running' || taskStatus === 'pending'"
        class="eval-progress"
      />
      <div class="eval-task-meta">
        <span>当前阶段: <b>{{ taskStageLabel }}</b></span>
        <span>已耗时: <b>{{ elapsedText }}</b></span>
        <span>模式: <b>{{ taskModeLabel }}</b></span>
        <span v-if="taskSampleSize">题数: <b>{{ taskSampleSize }}</b></span>
      </div>
      <el-alert
        v-if="taskError"
        :title="taskError"
        type="error"
        :closable="false"
        show-icon
        class="mt-16"
      />
    </el-card>

    <!-- 1. AI 能力总览 -->
    <el-card class="mb-16" shadow="never">
      <template #header>
        <div class="card-header">
          <span>AI 能力总览</span>
          <span v-if="summary && summary.generated_at" class="meta-secondary">
            最近评估: {{ summary.generated_at }}
          </span>
        </div>
      </template>
      <el-row :gutter="16" v-loading="loading">
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-card stat-rag">
            <div class="stat-label">RAG 综合评分</div>
            <div class="stat-value">{{ ragScoreAvg }}</div>
            <div class="stat-sub">命中率 {{ formatRate(summary && summary.context_hit_rate) }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-card stat-ai">
            <div class="stat-label">AI 成功率</div>
            <div class="stat-value">{{ formatRate(summary && summary.ai_success_rate) }}</div>
            <div class="stat-sub">{{ summary && summary.ai_total_calls || 0 }} 次调用</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-card stat-perf">
            <div class="stat-label">P95 耗时</div>
            <div class="stat-value">{{ formatMs(summary && summary.ai_p95_latency_ms) }}</div>
            <div class="stat-sub">目标 &lt; 10000ms</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6">
          <div class="stat-card stat-cost">
            <div class="stat-label">Token 成本</div>
            <div class="stat-value">¥{{ formatCost(summary && summary.estimated_cost_rmb) }}</div>
            <div class="stat-sub">{{ summary && summary.total_tokens || 0 }} tokens</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 空数据 / PENDING 提示 -->
    <el-card v-if="!loading && (!summary || !summary.total_questions)" class="mb-16" shadow="never">
      <el-empty description="尚未执行评估,点击右上角「执行评估」生成首份报告" />
    </el-card>

    <template v-if="summary && summary.total_questions">
      <!-- 2. RAG 评估 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <span>RAG 评估指标</span>
            <el-tag
              :type="statusTagType(summary.rag_status && summary.rag_status.status)"
              size="small"
            >
              {{ summary.rag_status && summary.rag_status.status }}
            </el-tag>
          </div>
        </template>
        <el-row :gutter="16">
          <el-col
            v-for="m in ragMetrics"
            :key="m.key"
            :xs="24"
            :sm="12"
            :md="6"
          >
            <div class="metric-card">
              <div class="metric-header">
                <span class="metric-name">{{ m.label }}</span>
                <el-tag
                  :type="metricPass(summary[m.key], m.target) ? 'success' : 'danger'"
                  size="small"
                >
                  {{ metricPass(summary[m.key], m.target) ? '达标' : '未达标' }}
                </el-tag>
              </div>
              <div class="metric-value">{{ formatNum(summary[m.key]) }}</div>
              <el-progress
                :percentage="toPercent(summary[m.key])"
                :color="metricPass(summary[m.key], m.target) ? '#67c23a' : '#f56c6c'"
                :stroke-width="8"
              />
              <div class="metric-target">目标 ≥ {{ m.target }}</div>
            </div>
          </el-col>
        </el-row>
        <el-alert
          v-if="summary.rag_status && summary.rag_status.reason"
          :title="summary.rag_status.reason"
          :type="alertType(summary.rag_status.status)"
          :closable="false"
          show-icon
          class="mt-16"
        />
      </el-card>

      <!-- 3. Agent 评估 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <span>Agent 能力评估</span>
            <el-tag
              :type="statusTagType(summary.ai_status && summary.ai_status.status)"
              size="small"
            >
              {{ summary.ai_status && summary.ai_status.status }}
            </el-tag>
          </div>
        </template>
        <el-row :gutter="16">
          <el-col :xs="24" :sm="8">
            <div class="agent-stat">
              <div class="agent-label">Agent 任务总数</div>
              <div class="agent-value">{{ summary.agent_task_total || 0 }}</div>
              <div class="agent-sub">完成率 {{ formatRate(summary.agent_completion_rate) }}</div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="8">
            <div class="agent-stat">
              <div class="agent-label">工具调用次数</div>
              <div class="agent-value">{{ summary.tool_call_total || 0 }}</div>
              <div class="agent-sub">工具成功率 {{ formatRate(summary.tool_success_rate) }}</div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="8">
            <div class="agent-stat">
              <div class="agent-label">Agent 类型数</div>
              <div class="agent-value">{{ agentTypeCount }}</div>
              <div class="agent-sub">contract_review / generation / bid</div>
            </div>
          </el-col>
        </el-row>

        <!-- 工具调用明细 -->
        <el-table
          v-if="summary.agent_tool_breakdown && summary.agent_tool_breakdown.length"
          :data="summary.agent_tool_breakdown"
          stripe
          border
          size="small"
          class="mt-16"
        >
          <el-table-column label="工具名称" prop="tool" min-width="200" />
          <el-table-column label="调用次数" prop="calls" width="100" align="center" />
          <el-table-column label="成功" prop="success" width="80" align="center" />
          <el-table-column label="失败" prop="failed" width="80" align="center" />
          <el-table-column label="成功率" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="row.success_rate >= 0.95 ? 'success' : 'warning'" size="small">
                {{ formatRate(row.success_rate) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="累计耗时(ms)" prop="total_duration_ms" width="130" align="center" />
        </el-table>
      </el-card>

      <!-- 4. 测试环境说明 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <span>测试环境说明</span>
          </div>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="知识库文档总数">
            {{ (summary.test_environment && summary.test_environment.knowledge_total_documents) || 0 }} 份
          </el-descriptions-item>
          <el-descriptions-item label="命中文档数">
            {{ (summary.test_environment && summary.test_environment.knowledge_hit_documents) || 0 }} 份
          </el-descriptions-item>
          <el-descriptions-item label="Embedding 完成数">
            {{ (summary.test_environment && summary.test_environment.knowledge_embedding_completed) || 0 }} 份
          </el-descriptions-item>
          <el-descriptions-item label="知识库命中率">
            {{ formatRate(summary.test_environment && summary.test_environment.knowledge_hit_rate) }}
          </el-descriptions-item>
          <el-descriptions-item label="测试问题数">
            {{ summary.total_questions }} 题(命中 {{ summary.context_hit_count }} 题)
          </el-descriptions-item>
          <el-descriptions-item label="Embedding 模型">
            {{ summary.test_environment && summary.test_environment.embedding_model }}
          </el-descriptions-item>
          <el-descriptions-item label="LLM 模型">
            {{ summary.test_environment && summary.test_environment.llm_model }}
          </el-descriptions-item>
          <el-descriptions-item label="Retriever">
            {{ summary.test_environment && summary.test_environment.retriever }}
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="summary.reason"
          :title="summary.reason"
          :type="alertType(summary.status)"
          :closable="false"
          show-icon
          class="mt-16"
        />
      </el-card>

      <!-- Sprint 8.7: 评估性能统计(cache 命中率 / 各阶段耗时) -->
      <el-card v-if="summary.performance" class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <span>评估性能统计</span>
            <el-tag size="small" effect="plain">Sprint 8.7 优化</el-tag>
          </div>
        </template>
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12" :md="6">
            <div class="perf-stat">
              <div class="perf-label">RAG 总耗时</div>
              <div class="perf-value">{{ formatSeconds(summary.performance.total_seconds) }}</div>
              <div class="perf-sub">目标 quick &lt; 30s / standard &lt; 120s</div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6">
            <div class="perf-stat">
              <div class="perf-label">缓存命中率</div>
              <div class="perf-value">
                {{ formatRate(summary.performance.cache_hit_rate) }}
              </div>
              <div class="perf-sub">
                命中 {{ summary.performance.cache_hit_count || 0 }}/{{ summary.performance.cache_total_count || 0 }}
              </div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6">
            <div class="perf-stat">
              <div class="perf-label">检索 / 重排耗时</div>
              <div class="perf-value">
                {{ formatSeconds(summary.performance.retrieval_seconds) }} /
                {{ formatSeconds(summary.performance.rerank_seconds) }}
              </div>
              <div class="perf-sub">dense / rerank(评估 quick 模式已关闭 rerank)</div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6">
            <div class="perf-stat">
              <div class="perf-label">Embedding / 指标耗时</div>
              <div class="perf-value">
                {{ formatSeconds(summary.performance.embedding_seconds) }} /
                {{ formatSeconds(summary.performance.metric_seconds) }}
              </div>
              <div class="perf-sub">
                并行 worker: {{ summary.performance.parallel_workers || 1 }} · rerank: {{ summary.performance.use_rerank ? '开' : '关' }}
              </div>
            </div>
          </el-col>
        </el-row>
      </el-card>
    </template>

    <!-- 5. 历史报告 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>历史评估报告</span>
          <el-button text :icon="Refresh" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table
        v-loading="historyLoading"
        :data="historyData"
        stripe
        border
        size="small"
        :empty-text="historyLoading ? '加载中...' : '暂无历史评估记录'"
      >
        <el-table-column label="报告编号" prop="report_no" min-width="200" />
        <el-table-column label="评估时间" prop="created_time" min-width="160" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题目数" prop="total_questions" width="80" align="center" />
        <el-table-column label="命中率" width="100" align="center">
          <template #default="{ row }">
            {{ formatRate(row.context_hit_rate) }}
          </template>
        </el-table-column>
        <el-table-column label="Faithfulness" width="120" align="center">
          <template #default="{ row }">
            {{ formatNum(row.faithfulness) }}
          </template>
        </el-table-column>
        <el-table-column label="AI 成功率" width="110" align="center">
          <template #default="{ row }">
            {{ formatRate(row.ai_success_rate) }}
          </template>
        </el-table-column>
        <el-table-column label="操作者" prop="generated_by_username" width="110" align="center" />
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="viewHistoryDetail(row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="historyPage"
          v-model:page-size="historySize"
          :total="historyTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadHistory"
          @current-change="loadHistory"
        />
      </div>
    </el-card>

    <!-- 历史详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      title="历史评估详情"
      width="80%"
      top="5vh"
      destroy-on-close
    >
      <el-descriptions
        v-if="historyDetail"
        :column="2"
        border
        size="small"
        class="mb-16"
      >
        <el-descriptions-item label="报告编号">{{ historyDetail.report_no }}</el-descriptions-item>
        <el-descriptions-item label="评估时间">{{ historyDetail.created_time }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTagType(historyDetail.metrics && historyDetail.metrics.status)" size="small">
            {{ historyDetail.metrics && historyDetail.metrics.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="操作者">
          {{ historyDetail.generated_by_username }}
        </el-descriptions-item>
      </el-descriptions>
      <el-input
        v-if="historyDetail && historyDetail.summary"
        :model-value="historyDetail.summary"
        type="textarea"
        :rows="10"
        readonly
      />
      <el-empty v-else description="无摘要信息" />
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * AI 评估(Sprint 8.5)
 *
 * 功能:
 * 1. AI 能力总览:RAG 评分 / AI 成功率 / P95 耗时 / Token 成本
 * 2. RAG 评估:Faithfulness / Answer Relevancy / Context Precision / Context Recall(带达标判定)
 * 3. Agent 评估:任务总数 / 完成率 / 工具调用次数 / 工具调用明细
 * 4. 测试环境说明:知识库文档数 / 命中数 / 命中率 / 模型信息
 * 5. 历史报告:列表 + 详情查看
 * 6. 执行评估按钮:调用 POST /evaluation/run(admin)
 *
 * 权限:仅 admin 可访问(路由守卫 + 后端 role_required 双重保证)
 */
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DataLine, Refresh, VideoPlay } from '@element-plus/icons-vue'
import {
  getEvaluationSummary,
  listEvaluationHistory,
  getEvaluationHistoryDetail,
  runEvaluation,
  getEvaluationTask,
} from '@/api/evaluation'

// ---------- summary 状态 ----------
const loading = ref(false)
const runLoading = ref(false)
const summary = ref(null)

// ---------- Sprint 8.6.1: 异步任务 + 评估模式 ----------
// 模式定义(与后端 EVALUATION_MODES 对齐)
const evalModes = [
  { value: 'quick', label: '快速验证', desc: '10 题快速验证,规则级,不消耗 Token,开发调参用', sample: 10 },
  { value: 'standard', label: '标准评估', desc: '51 题完整评估,规则级,不消耗 Token,生产验收用', sample: 51 },
  { value: 'full', label: '完整评估', desc: '51 题 + LLM Judge,调用 DeepSeek 生成答案,消耗 Token', sample: 51 },
]
const evalMode = ref('standard')

// 任务状态(轮询 GET /evaluation/task/{id})
const taskId = ref(null)
const taskStatus = ref(null) // pending | running | success | failed
const taskProgress = ref(0)
const taskStage = ref('creating')
const taskError = ref(null)
const taskSampleSize = ref(null)
const elapsedSeconds = ref(0)

// 阶段中文文案
const STAGE_LABELS = {
  creating: '创建任务…',
  rag_evaluation: 'RAG 检索评估(占用大部分耗时)…',
  ai_metrics: 'AI 调用质量统计…',
  agent_metrics: 'Agent 工具统计…',
  report_generation: '生成评估报告…',
  completed: '已完成',
  failed: '执行失败',
}

let taskPollTimer = null
let elapsedTimer = null

// ---------- RAG 指标配置(与后端 RAG_TARGETS 对齐) ----------
const ragMetrics = [
  { key: 'faithfulness', label: 'Faithfulness (忠实度)', target: 0.85 },
  { key: 'answer_relevancy', label: 'Answer Relevancy (相关性)', target: 0.85 },
  { key: 'context_precision', label: 'Context Precision (精确度)', target: 0.80 },
  { key: 'context_recall', label: 'Context Recall (召回率)', target: 0.80 },
]

// ---------- 历史报告状态 ----------
const historyLoading = ref(false)
const historyData = ref([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historySize = ref(10)
const detailVisible = ref(false)
const historyDetail = ref(null)

// ---------- 计算属性 ----------
const ragScoreAvg = computed(() => {
  if (!summary.value) return '0.00'
  const vals = ragMetrics.map((m) => Number(summary.value[m.key]) || 0)
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length
  return avg.toFixed(4)
})

const agentTypeCount = computed(() => {
  if (!summary.value || !summary.value.ai_per_agent) return 0
  return Object.keys(summary.value.ai_per_agent).length
})

// ---------- Sprint 8.6.1: 任务相关计算属性 ----------
const taskActive = computed(() => {
  return taskStatus.value === 'pending' || taskStatus.value === 'running'
})
const taskFinished = computed(() => {
  return taskStatus.value === 'success' || taskStatus.value === 'failed'
})
const taskStatusLabel = computed(() => {
  const map = { pending: '等待执行', running: '执行中', success: '已完成', failed: '执行失败' }
  return map[taskStatus.value] || '-'
})
const taskTagType = computed(() => {
  const map = { pending: 'warning', running: 'primary', success: 'success', failed: 'danger' }
  return map[taskStatus.value] || 'info'
})
const taskStageLabel = computed(() => {
  return STAGE_LABELS[taskStage.value] || taskStage.value || '-'
})
const taskModeLabel = computed(() => {
  const m = evalModes.find((x) => x.value === evalMode.value)
  return m ? m.label : evalMode.value
})
const elapsedText = computed(() => {
  const s = Math.floor(elapsedSeconds.value)
  const mm = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
})
const evalModeTip = computed(() => {
  const m = evalModes.find((x) => x.value === evalMode.value)
  return m ? `${m.label}:${m.desc}` : ''
})

// ---------- 格式化工具 ----------
const formatRate = (v) => {
  if (v == null) return '-'
  return `${(Number(v) * 100).toFixed(2)}%`
}
const formatNum = (v) => {
  if (v == null) return '-'
  return Number(v).toFixed(4)
}
const formatMs = (v) => {
  if (v == null) return '-'
  return `${v}ms`
}
const formatSeconds = (v) => {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return `${n.toFixed(2)}s`
}
const formatCost = (v) => {
  if (v == null) return '0.0000'
  return Number(v).toFixed(4)
}
const toPercent = (v) => {
  if (v == null) return 0
  return Math.min(100, Math.round(Number(v) * 100))
}
const metricPass = (v, target) => {
  if (v == null) return false
  return Number(v) >= target
}
const statusTagType = (status) => {
  if (status === 'PASS') return 'success'
  if (status === 'PENDING') return 'warning'
  if (status === 'FAIL') return 'danger'
  return 'info'
}
const alertType = (status) => {
  if (status === 'PASS') return 'success'
  if (status === 'PENDING') return 'warning'
  if (status === 'FAIL') return 'error'
  return 'info'
}

// ---------- 数据加载 ----------
const loadSummary = async () => {
  loading.value = true
  try {
    const res = await getEvaluationSummary()
    summary.value = res.data || null
  } catch (e) {
    // 错误已由拦截器提示
    summary.value = null
  } finally {
    loading.value = false
  }
}

const loadHistory = async () => {
  historyLoading.value = true
  try {
    const res = await listEvaluationHistory({
      page: historyPage.value,
      size: historySize.value,
    })
    historyData.value = res.data.items || []
    historyTotal.value = res.data.total || 0
  } catch (e) {
    historyData.value = []
    historyTotal.value = 0
  } finally {
    historyLoading.value = false
  }
}

const viewHistoryDetail = async (row) => {
  try {
    const res = await getEvaluationHistoryDetail(row.id)
    historyDetail.value = res.data || null
    detailVisible.value = true
  } catch (e) {
    // 错误已由拦截器提示
  }
}

// ---------- 执行评估(Sprint 8.6.1 异步化) ----------
// POST /evaluation/run 立即返回任务 → 轮询 GET /evaluation/task/{id}
// → success 后自动刷新 summary + history
const handleRunEvaluation = async () => {
  const modeInfo = evalModes.find((x) => x.value === evalMode.value)
  const confirmMsg = `将执行一次 AI 评估。\n模式:${modeInfo.label}(${modeInfo.desc})。\n` +
    `评估在后台异步执行,页面可自由操作,完成后自动刷新结果。是否继续?`
  try {
    await ElMessageBox.confirm(confirmMsg, '执行评估', {
      confirmButtonText: '执行',
      cancelButtonText: '取消',
      type: 'info',
    })
  } catch (e) {
    return // 用户取消
  }

  runLoading.value = true
  try {
    const res = await runEvaluation({
      mode: evalMode.value,
      period_days: 60,
    })
    const task = res.data
    if (!task || !task.task_id) {
      ElMessage.error('任务创建失败:未返回 task_id')
      return
    }
    ElMessage.success('评估任务已提交,后台执行中')
    startTaskPolling(task.task_id)
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    runLoading.value = false
  }
}

// ---------- 任务轮询 + 耗时计时 ----------
const startTaskPolling = (tid) => {
  stopTaskTimers()
  taskId.value = tid
  taskStatus.value = 'pending'
  taskProgress.value = 0
  taskStage.value = 'creating'
  taskError.value = null
  taskSampleSize.value = null
  elapsedSeconds.value = 0
  // 已耗时计时器(每秒 +1)
  elapsedTimer = setInterval(() => {
    elapsedSeconds.value += 1
  }, 1000)
  // 轮询任务进度
  taskPollTimer = setInterval(async () => {
    try {
      const res = await getEvaluationTask(tid)
      const t = res.data
      taskStatus.value = t.status
      taskProgress.value = t.progress || 0
      taskStage.value = t.stage || taskStage.value
      taskSampleSize.value = t.sample_size
      if (t.status === 'success') {
        stopTaskTimers()
        taskProgress.value = 100
        ElMessage.success('评估执行完成')
        await refreshAfterDone()
      } else if (t.status === 'failed') {
        stopTaskTimers()
        taskError.value = t.error || '评估执行失败,请查看后端日志'
        ElMessage.error('评估执行失败')
        await refreshAfterDone()
      }
    } catch (e) {
      // 单次轮询失败(网络抖动)不中断,下轮重试
    }
  }, 2000)
}

const stopTaskTimers = () => {
  if (taskPollTimer) {
    clearInterval(taskPollTimer)
    taskPollTimer = null
  }
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

// 任务结束后刷新 summary + 历史列表
const refreshAfterDone = async () => {
  await loadSummary()
  historyPage.value = 1
  await loadHistory()
}

// 页面卸载清理定时器,避免内存泄漏
onBeforeUnmount(() => {
  stopTaskTimers()
})

// ---------- 初始化 ----------
onMounted(() => {
  loadSummary()
  loadHistory()
})
</script>

<style scoped>
.mb-16 {
  margin-bottom: 16px;
}
.mt-16 {
  margin-top: 16px;
}
.meta-secondary {
  color: #909399;
  font-size: 12px;
}
.page-container {
  padding: 0;
}
.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.overview-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.title-icon {
  font-size: 32px;
  color: #409eff;
}
.title-text {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.title-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
}
.overview-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 统计卡片 */
.stat-card {
  padding: 20px;
  border-radius: 8px;
  text-align: center;
  margin-bottom: 16px;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 4px;
}
.stat-sub {
  font-size: 12px;
  color: #909399;
}
.stat-rag {
  background: #ecf5ff;
  color: #409eff;
}
.stat-ai {
  background: #f0f9eb;
  color: #67c23a;
}
.stat-perf {
  background: #fdf6ec;
  color: #e6a23c;
}
.stat-cost {
  background: #fef0f0;
  color: #f56c6c;
}

/* RAG 指标卡片 */
.metric-card {
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 16px;
}
.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.metric-name {
  font-size: 13px;
  font-weight: 600;
}
.metric-value {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 8px;
}
.metric-target {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

/* Agent 统计 */
.agent-stat {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  text-align: center;
  margin-bottom: 16px;
}
.agent-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
.agent-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 4px;
}
.agent-sub {
  font-size: 12px;
  color: #909399;
}

/* Sprint 8.7: 评估性能统计 */
.perf-stat {
  padding: 16px;
  background: #f4f4f5;
  border-radius: 8px;
  text-align: center;
  margin-bottom: 16px;
}
.perf-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}
.perf-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 4px;
}
.perf-sub {
  font-size: 12px;
  color: #909399;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* Sprint 8.6.1: 异步任务进度卡片 */
.eval-task-card {
  border-left: 4px solid #409eff;
}
.eval-progress {
  margin-bottom: 12px;
}
.eval-task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  font-size: 13px;
  color: #606266;
}
.eval-task-meta b {
  color: #303133;
  font-weight: 600;
}
</style>
