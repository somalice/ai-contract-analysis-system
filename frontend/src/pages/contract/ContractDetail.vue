<template>
  <!-- 合同详情页:合同信息 / 文件信息 / 创建人 / AI 分析(任务进度+字段) / 状态流转 -->
  <div class="page-container" v-loading="loading">
    <!-- 顶部操作栏 -->
    <el-card class="action-card mb-16" shadow="never">
      <div class="action-bar">
        <el-button :icon="Back" @click="router.back()">返回</el-button>
        <div class="action-right">
          <!-- 开始分析 / 重新分析按钮 -->
          <el-button
            v-if="canAnalyze"
            type="primary"
            :icon="MagicStick"
            :loading="analyzing"
            :disabled="analyzing || contract?.analysis_status === 'processing' || reviewing"
            @click="handleTriggerAnalysis"
          >
            {{ analysisButtonText }}
          </el-button>
          <!-- AI 风险审核按钮(Sprint 5:仅 admin/manager + 已完成分析) -->
          <el-button
            v-if="canReview"
            type="danger"
            :icon="Warning"
            :loading="reviewing"
            :disabled="reviewing || analyzing"
            @click="handleTriggerReview"
          >
            AI 风险审核
          </el-button>
          <StatusTag
            v-if="contract"
            :status="contract.status"
            :show-analysis="true"
            :analysis-status="contract.analysis_status"
          />
        </div>
      </div>
    </el-card>

    <template v-if="contract">
      <!-- 基本信息 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Document /></el-icon>
            <span>合同基本信息</span>
          </div>
        </template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="合同编号">
            {{ contract.contract_no }}
          </el-descriptions-item>
          <el-descriptions-item label="合同标题">
            {{ contract.title }}
          </el-descriptions-item>
          <el-descriptions-item label="合同类型">
            {{ contract.contract_type }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :status="contract.status" />
          </el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">
            {{ contract.description || '无' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 文件 + 创建人信息 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-card class="mb-16" shadow="never">
            <template #header>
              <div class="card-header">
                <el-icon><Files /></el-icon>
                <span>文件信息</span>
              </div>
            </template>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="文件名">
                {{ contract.file_info?.name || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="文件大小">
                {{ formatFileSize(contract.file_info?.size) }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card class="mb-16" shadow="never">
            <template #header>
              <div class="card-header">
                <el-icon><User /></el-icon>
                <span>创建人</span>
              </div>
            </template>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="用户名">
                {{ contract.creator?.username || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="角色">
                <el-tag size="small" :type="creatorRoleTagType">
                  {{ creatorRoleLabel }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="创建时间">
                {{ formatTime(contract.created_time) }}
              </el-descriptions-item>
              <el-descriptions-item label="更新时间">
                {{ formatTime(contract.updated_time) }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
      </el-row>

      <!-- AI 分析结果(Sprint 3 升级:任务进度 + 字段展示) -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><MagicStick /></el-icon>
            <span>AI 分析结果</span>
            <el-tag
              v-if="task"
              size="small"
              :type="taskStatusTagType"
              class="header-tag"
            >
              {{ taskStatusLabel }}
            </el-tag>
            <el-tag
              v-else-if="contract.analysis_status"
              size="small"
              :type="analysisTagType"
              class="header-tag"
            >
              {{ analysisStatusLabel }}
            </el-tag>
          </div>
        </template>

        <!-- 分析任务进度(6 个 Stage) -->
        <div v-if="task && task.stages_log" class="stages-progress">
          <div class="stages-title">分析进度</div>
          <div class="stages-flow">
            <div
              v-for="stage in stagesWithStatus"
              :key="stage.name"
              class="stage-item"
              :class="stage.cssClass"
            >
              <div class="stage-icon">
                <el-icon v-if="stage.status === 'success'"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="stage.status === 'failed'" class="is-failed"><CircleCloseFilled /></el-icon>
                <el-icon v-else-if="stage.status === 'running'" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="stage.status === 'skipped'"><RemoveFilled /></el-icon>
                <span v-else class="stage-index">{{ stage.index }}</span>
              </div>
              <div class="stage-label">{{ stage.label }}</div>
              <div class="stage-status">{{ stage.statusLabel }}</div>
            </div>
          </div>
          <!-- 失败原因 -->
          <el-alert
            v-if="task.status === 'failed' && task.error_message"
            type="error"
            :closable="false"
            show-icon
            class="mt-12"
          >
            <template #title>失败原因:{{ task.error_message }}</template>
          </el-alert>
        </div>

        <!-- 字段展示 -->
        <div v-if="fields.length > 0" class="fields-section">
          <div class="fields-title">
            提取字段({{ foundFieldsCount }}/{{ fields.length }} 个有值)
            <el-tag v-if="fieldsSourceLabel" size="small" type="info" class="ml-8">
              {{ fieldsSourceLabel }}
            </el-tag>
          </div>
          <el-table :data="fields" border stripe class="mt-8">
            <el-table-column label="字段" width="140">
              <template #default="{ row }">
                {{ row.field_label || row.field_name }}
              </template>
            </el-table-column>
            <el-table-column label="值" min-width="200">
              <template #default="{ row }">
                <span v-if="row.field_value" class="field-value">{{ row.field_value }}</span>
                <span v-else class="field-null">未提取到</span>
              </template>
            </el-table-column>
            <el-table-column label="置信度" width="180">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round((row.confidence || 0) * 100)"
                  :status="confidenceStatus(row.confidence)"
                  :stroke-width="14"
                  :text-inside="true"
                />
              </template>
            </el-table-column>
            <el-table-column label="来源" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.source_text" class="field-source">{{ row.source_text }}</span>
                <span v-else class="field-null">-</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 待分析 / 无结果占位 -->
        <el-empty
          v-if="!task && fields.length === 0"
          :description="emptyDescription"
        >
          <el-button
            v-if="canAnalyze && contract.analysis_status === 'pending'"
            type="primary"
            :icon="MagicStick"
            :loading="analyzing"
            @click="handleTriggerAnalysis"
          >
            开始 AI 分析
          </el-button>
        </el-empty>

        <!-- 旧版 analysis_result 兼容展示(无 contract_fields 时) -->
        <div
          v-if="fields.length === 0 && contract.analysis_result && !contract.analysis_result.error
                && contract.analysis_status === 'completed'"
          class="legacy-result"
        >
          <el-alert type="info" :closable="false" show-icon class="mb-12">
            <template #title>
              该合同为 Sprint 2 旧数据,展示 legacy analysis_result(Sprint 3 字段请点"重新分析")
            </template>
          </el-alert>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="合同名称">
              {{ contract.analysis_result.contract_name || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="签署日期">
              {{ contract.analysis_result.signing_date || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="甲方" :span="2">
              {{ contract.analysis_result.party_a || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="乙方" :span="2">
              {{ contract.analysis_result.party_b || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="合同金额" :span="2">
              <span class="amount-text">
                {{ contract.analysis_result.amount || '-' }}
              </span>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-card>

      <!-- 状态流转 -->
      <el-card v-if="canUpdateStatus" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Switch /></el-icon>
            <span>状态流转</span>
          </div>
        </template>
        <div class="status-flow">
          <span class="current-status-label">当前状态:</span>
          <StatusTag :status="contract.status" />
          <span class="flow-arrow" v-if="availableTransitions.length > 0">→</span>
          <template v-if="availableTransitions.length > 0">
            <el-button
              v-for="target in availableTransitions"
              :key="target"
              :type="statusButtonType(target)"
              size="small"
              :loading="statusUpdating"
              @click="handleStatusTransition(target)"
            >
              流转至「{{ STATUS_LABELS[target] }}」
            </el-button>
          </template>
          <el-tag v-else type="info" class="terminal-tag">终态,不可流转</el-tag>
        </div>
      </el-card>
    </template>

    <!-- 加载中占位 -->
    <el-empty v-else-if="!loading" description="合同不存在或加载失败" />
  </div>
</template>

<script setup>
/**
 * 合同详情页(Sprint 3 - v0.5.0 升级)
 *
 * 新增功能:
 * - AI 分析任务进度展示(6 个 Stage:extract/ocr/clean/chunk/llm/save)
 * - 结构化字段表格(8 字段 + confidence 进度条 + 来源文本)
 * - "开始分析 / 重新分析"按钮(触发 POST /contracts/{id}/analysis)
 * - 数据来源标识(contract_fields / legacy_json / empty)
 * - 兼容 Sprint 2 旧合同(无 contract_fields 时降级读 analysis_result)
 *
 * 权限:
 * - admin / contract_manager:可分析任意合同 + 流转状态
 * - employee:仅可分析/查看自己的合同(后端校验),无状态流转按钮
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Back, Document, Files, User, MagicStick, Switch, Loading,
  CircleCheckFilled, CircleCloseFilled, RemoveFilled, Warning,
} from '@element-plus/icons-vue'
import {
  getContractDetail,
  updateContractStatus,
  triggerContractAnalysis,
  getContractFields,
} from '@/api/contract'
import { triggerContractReview } from '@/api/review'
import StatusTag from '@/components/contract/StatusTag.vue'
import { useAuthStore } from '@/store/auth'
import {
  STATUS_LABELS,
  STATUS_TAG_TYPES,
  STATUS_TRANSITIONS,
  ANALYSIS_STATUS,
  ANALYSIS_STATUS_LABELS,
  ANALYSIS_STATUS_TAG_TYPES,
  TASK_STATUS,
  TASK_STATUS_LABELS,
  TASK_STATUS_TAG_TYPES,
  PIPELINE_STAGES,
  STAGE_LABELS,
  STAGE_STATUS,
  STAGE_STATUS_LABELS,
  STAGE_STATUS_TAG_TYPES,
  ROLE_LABELS,
  ROLES,
} from '@/utils/constants'
import { formatTime, formatFileSize } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const statusUpdating = ref(false)
const analyzing = ref(false)
const reviewing = ref(false)
const contract = ref(null)
const task = ref(null)         // 最近分析任务
const fields = ref([])          // 字段列表
const fieldsSource = ref('empty') // 数据来源

// ---------- 权限 ----------
const canUpdateStatus = computed(
  () => authStore.isAdmin || authStore.isManager
)
// employee 也可分析自己的合同(后端校验归属);前端按钮对登录用户均可见
const canAnalyze = computed(() => !!contract.value)
// AI 风险审核:仅 admin / contract_manager 可触发,且需已完成 AI 分析
const canReview = computed(
  () => (authStore.isAdmin || authStore.isManager)
    && !!contract.value
    && contract.value.analysis_status === ANALYSIS_STATUS.COMPLETED
)

// ---------- 可流转状态列表 ----------
const availableTransitions = computed(() => {
  if (!contract.value) return []
  return STATUS_TRANSITIONS[contract.value.status] || []
})

// ---------- 角色显示 ----------
const creatorRoleLabel = computed(
  () => ROLE_LABELS[contract.value?.creator?.role] || '-'
)
const creatorRoleTagType = computed(() => {
  const role = contract.value?.creator?.role
  if (role === ROLES.ADMIN) return 'danger'
  if (role === ROLES.CONTRACT_MANAGER) return 'warning'
  return 'info'
})

// ---------- AI 分析状态显示(合同维度) ----------
const analysisStatusLabel = computed(
  () => ANALYSIS_STATUS_LABELS[contract.value?.analysis_status] || '-'
)
const analysisTagType = computed(
  () => ANALYSIS_STATUS_TAG_TYPES[contract.value?.analysis_status] || 'info'
)

// ---------- 任务状态显示 ----------
const taskStatusLabel = computed(
  () => TASK_STATUS_LABELS[task.value?.status] || '-'
)
const taskStatusTagType = computed(
  () => TASK_STATUS_TAG_TYPES[task.value?.status] || 'info'
)

// ---------- 分析按钮文案 ----------
const analysisButtonText = computed(() => {
  const s = contract.value?.analysis_status
  if (analyzing.value) return '分析中...'
  if (s === ANALYSIS_STATUS.PENDING) return '开始分析'
  if (s === ANALYSIS_STATUS.FAILED) return '重新分析'
  if (s === ANALYSIS_STATUS.COMPLETED) return '重新分析'
  return '开始分析'
})

// ---------- Stage 进度计算 ----------
// 将 6 个 Stage 与 stages_log 匹配,标注每个 Stage 的状态
const stagesWithStatus = computed(() => {
  if (!task.value) return []
  const logMap = {}
  if (Array.isArray(task.value.stages_log)) {
    task.value.stages_log.forEach((s) => {
      logMap[s.stage] = s
    })
  }
  // 判断当前执行到哪一步(用于 running 标记)
  const currentStage = task.value.current_stage
  const taskStatus = task.value.status

  return PIPELINE_STAGES.map((name, idx) => {
    const log = logMap[name]
    let status = 'pending'
    if (log) {
      status = log.status // success / skipped / failed
    } else if (taskStatus === TASK_STATUS.RUNNING && name === currentStage) {
      status = 'running'
    } else if (taskStatus === TASK_STATUS.SUCCESS || taskStatus === TASK_STATUS.FAILED) {
      // 任务已结束但该 Stage 无日志 → 未执行
      status = 'pending'
    }

    const cssClass = `stage-${status}`
    return {
      name,
      index: idx + 1,
      label: STAGE_LABELS[name] || name,
      status,
      statusLabel: status === 'running' ? '执行中' : (STAGE_STATUS_LABELS[status] || '未执行'),
      cssClass,
    }
  })
})

// ---------- 字段统计 ----------
const foundFieldsCount = computed(
  () => fields.value.filter((f) => f.field_value).length
)
const fieldsSourceLabel = computed(() => {
  if (fieldsSource.value === 'contract_fields') return 'Pipeline 提取'
  if (fieldsSource.value === 'legacy_json') return 'Sprint 2 旧数据'
  return ''
})

// ---------- 空状态描述 ----------
const emptyDescription = computed(() => {
  const s = contract.value?.analysis_status
  if (s === ANALYSIS_STATUS.PENDING) return '该合同尚未进行 AI 分析'
  if (s === ANALYSIS_STATUS.FAILED) return '上次分析失败,可重新分析'
  return '暂无 AI 分析结果'
})

// ---------- 状态按钮类型 ----------
function statusButtonType(target) {
  return STATUS_TAG_TYPES[target] === 'success' ? 'success' : 'warning'
}

// ---------- 置信度进度条状态 ----------
function confidenceStatus(conf) {
  const v = conf || 0
  if (v >= 0.8) return 'success'
  if (v >= 0.5) return '' // 默认(蓝)
  if (v > 0) return 'warning'
  return 'exception'
}

/**
 * 加载合同详情 + 字段
 */
async function loadDetail() {
  loading.value = true
  try {
    const id = route.params.id
    const res = await getContractDetail(id)
    contract.value = res.data.contract
    // 并行加载字段
    loadFields(id)
  } catch (err) {
    contract.value = null
  } finally {
    loading.value = false
  }
}

/**
 * 加载合同字段(优先 contract_fields,降级由后端处理)
 */
async function loadFields(id) {
  try {
    const res = await getContractFields(id)
    fields.value = res.data.fields || []
    fieldsSource.value = res.data.source || 'empty'
    task.value = res.data.task || null
    // 若有任务但 stages_log 不完整(任务可能在 running),保留后端返回的 task
  } catch (err) {
    // 字段加载失败不影响详情展示
    fields.value = []
    fieldsSource.value = 'empty'
  }
}

/**
 * 触发 AI 分析
 */
async function handleTriggerAnalysis() {
  if (!contract.value) return
  // 确认对话框(已完成/失败时提示重新分析)
  const s = contract.value.analysis_status
  if (s === ANALYSIS_STATUS.COMPLETED || s === ANALYSIS_STATUS.FAILED) {
    try {
      await ElMessageBox.confirm(
        '重新分析将创建新任务并覆盖字段展示,确定继续吗?',
        '重新分析确认',
        {
          confirmButtonText: '确定分析',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
    } catch {
      return
    }
  }

  analyzing.value = true
  // 立即更新 UI 为 processing
  if (contract.value) {
    contract.value.analysis_status = ANALYSIS_STATUS.PROCESSING
  }

  try {
    const res = await triggerContractAnalysis(contract.value.id)
    // 同步刷新合同状态 + 任务 + 字段
    if (res.data.contract) {
      contract.value = res.data.contract
    }
    if (res.data.task) {
      task.value = res.data.task
    }
    // 加载最新字段
    await loadFields(contract.value.id)

    const taskStatus = res.data.task?.status
    if (taskStatus === TASK_STATUS.SUCCESS) {
      ElMessage.success('AI 分析完成')
    } else if (taskStatus === TASK_STATUS.FAILED) {
      ElMessage.warning('AI 分析失败,请查看任务详情')
    } else {
      ElMessage.info('分析任务已执行')
    }
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示
    // 恢复 analysis_status(刷新详情)
    loadDetail()
  } finally {
    analyzing.value = false
  }
}

/**
 * 触发 AI 风险审核(Sprint 5 - v0.7.0)
 * 同步执行 Contract Review Agent(ReAct 循环),耗时 15–90s
 * 成功后跳转审核报告详情页
 */
async function handleTriggerReview() {
  if (!contract.value) return
  try {
    await ElMessageBox.confirm(
      '将启动 AI 风险审核(Agent 多轮分析 + RAG 检索),预计耗时 15–90 秒,请耐心等待。确定继续吗?',
      'AI 风险审核',
      {
        confirmButtonText: '开始审核',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }

  reviewing.value = true
  try {
    const res = await triggerContractReview(contract.value.id)
    const review = res.data.review
    if (review) {
      if (review.status === 'success') {
        ElMessage.success('AI 风险审核完成')
      } else {
        ElMessage.warning('审核任务执行完毕,请查看报告详情')
      }
      // 跳转审核报告详情页
      router.push(`/reviews/${review.id}`)
    }
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示
  } finally {
    reviewing.value = false
  }
}

/**
 * 状态流转
 */
async function handleStatusTransition(target) {
  try {
    await ElMessageBox.confirm(
      `确定将合同状态从「${STATUS_LABELS[contract.value.status]}」流转至「${STATUS_LABELS[target]}」吗?`,
      '状态流转确认',
      {
        confirmButtonText: '确定流转',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }

  statusUpdating.value = true
  try {
    const res = await updateContractStatus(contract.value.id, target)
    contract.value = res.data.contract
    ElMessage.success(`状态已流转至「${STATUS_LABELS[target]}」`)
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示
  } finally {
    statusUpdating.value = false
  }
}

// ---------- 初始化 ----------
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

.amount-text {
  font-size: 16px;
  font-weight: 600;
  color: #e6a23c;
}

.mb-12 {
  margin-bottom: 12px;
}

.mt-8 {
  margin-top: 8px;
}

.mt-12 {
  margin-top: 12px;
}

.ml-8 {
  margin-left: 8px;
}

/* ---------- Stage 进度 ---------- */
.stages-progress {
  margin-bottom: 16px;
}

.stages-title,
.fields-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
}

.stages-flow {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 12px;
  background-color: #fafafa;
  border-radius: 4px;
  overflow-x: auto;
}

.stage-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 90px;
  padding: 8px 4px;
  border-radius: 4px;
  position: relative;
}

.stage-item:not(:last-child)::after {
  content: '';
  position: absolute;
  right: -4px;
  top: 20px;
  width: 8px;
  height: 2px;
  background-color: #dcdfe6;
}

.stage-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background-color: #f0f0f0;
  color: #909399;
  margin-bottom: 6px;
}

.stage-success .stage-icon {
  background-color: #f0f9eb;
  color: #67c23a;
}

.stage-failed .stage-icon {
  background-color: #fef0f0;
  color: #f56c6c;
}

.stage-running .stage-icon {
  background-color: #fdf6ec;
  color: #e6a23c;
}

.stage-skipped .stage-icon {
  background-color: #f4f4f5;
  color: #909399;
}

.stage-running .is-loading {
  animation: rotating 1.5s linear infinite;
}

.stage-index {
  font-size: 13px;
  font-weight: 600;
  color: #909399;
}

.stage-label {
  font-size: 12px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 2px;
}

.stage-status {
  font-size: 11px;
  color: #909399;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---------- 字段表格 ---------- */
.fields-section {
  margin-top: 16px;
}

.field-value {
  color: #303133;
  font-weight: 500;
}

.field-null {
  color: #c0c4cc;
  font-style: italic;
}

.field-source {
  color: #606266;
  font-size: 13px;
}

/* ---------- 旧版结果 ---------- */
.legacy-result {
  margin-top: 8px;
}

/* ---------- 状态流转 ---------- */
.status-flow {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.current-status-label {
  color: #606266;
  font-size: 14px;
}

.flow-arrow {
  color: #909399;
  font-size: 16px;
  margin: 0 4px;
}

.terminal-tag {
  margin-left: 8px;
}
</style>
