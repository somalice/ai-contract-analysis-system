<template>
  <!-- 需求解析页:选择招标文件 → 展示 15 字段需求解析结果 -->
  <div class="page-container">
    <!-- 招标文件选择 -->
    <el-card class="filter-card mb-16" shadow="never">
      <template #header>
        <div class="card-header">
          <span>需求解析(招标文件 → 15 字段 Requirement)</span>
          <el-button
            v-if="selectedBidId && requirement"
            type="success"
            :icon="MagicStick"
            :disabled="requirement.status !== 'approved'"
            :title="requirement.status === 'approved' ? '生成投标文件' : '需求审核通过后才能生成投标文件'"
            @click="goGenerate"
          >
            生成投标文件
          </el-button>
        </div>
      </template>
      <el-form :inline="true" class="filter-form">
        <el-form-item label="招标文件">
          <el-select
            v-model="selectedBidId"
            placeholder="请选择已解析成功的招标文件"
            filterable
            clearable
            style="width: 400px"
            :loading="loadingBids"
            @change="handleBidChange"
          >
            <el-option
              v-for="b in bidOptions"
              :key="b.id"
              :label="`${b.bid_no} · ${b.title}`"
              :value="b.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="fetchBids">刷新列表</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 需求展示 -->
    <div v-loading="loading" element-loading-text="加载需求解析...">
      <template v-if="requirement">
        <!-- 质量指标 -->
        <el-card class="mb-16 status-overview" :class="overviewCardClass" shadow="never">
          <div class="overview-content">
            <div class="overview-left">
              <div class="overview-label">需求状态</div>
              <el-tag
                :type="statusTagType"
                effect="dark"
                size="large"
              >
                {{ statusLabel }}
              </el-tag>
            </div>
            <div class="overview-right">
              <div class="overview-stat">
                <span class="stat-label">字段数</span>
                <span class="stat-value">{{ requirement.field_count }} / 15</span>
              </div>
              <div class="overview-stat">
                <span class="stat-label">缺失数</span>
                <span class="stat-value warning">{{ requirement.missing_count }}</span>
              </div>
              <div class="overview-stat">
                <span class="stat-label">置信度</span>
                <span class="stat-value info">
                  {{ requirement.confidence ? (requirement.confidence * 100).toFixed(0) + '%' : '-' }}
                </span>
              </div>
              <div class="overview-stat">
                <span class="stat-label">需求编号</span>
                <span class="stat-value-small">{{ requirement.requirement_no }}</span>
              </div>
            </div>
          </div>
          <el-alert
            v-if="requirement.status === 'failed' && requirement.error_message"
            type="error"
            :closable="false"
            show-icon
            class="mt-12"
          >
            <template #title>解析失败:{{ requirement.error_message }}</template>
          </el-alert>
          <el-alert
            v-if="rejectComment"
            type="warning"
            :closable="false"
            show-icon
            class="mt-12"
          >
            <template #title>审核驳回:{{ rejectComment }}</template>
          </el-alert>
        </el-card>

        <!-- 需求审核操作区(Sprint 7.1 - v0.9.1):draft → reviewing → approved 闭环 -->
        <el-card
          v-if="canShowReviewPanel"
          class="mb-16 review-card"
          shadow="never"
        >
          <template #header>
            <div class="card-header">
              <el-icon><Checked /></el-icon>
              <span>需求审核</span>
              <el-tag :type="statusTagType" size="small" class="ml-8">{{ statusLabel }}</el-tag>
              <span v-if="requirement.version" class="review-version">{{ requirement.version }}</span>
            </div>
          </template>
          <div class="review-body">
            <!-- draft:提交审核 -->
            <template v-if="requirement.status === 'draft'">
              <div class="review-hint">需求处于草稿状态,提交审核后进入审核流程。审核通过后才能生成投标文件。</div>
              <div class="review-buttons">
                <el-button
                  v-if="isManager"
                  type="primary"
                  :icon="Promotion"
                  :loading="reviewLoading"
                  @click="handleSubmitReview"
                >
                  提交审核
                </el-button>
                <span v-else class="text-muted">仅管理员 / 合同管理员可提交审核</span>
              </div>
            </template>
            <!-- reviewing:审核通过 / 驳回 -->
            <template v-else-if="requirement.status === 'reviewing'">
              <div class="review-hint">需求审核中,请审核通过或驳回。驳回后需求回到草稿状态可重新提交。</div>
              <div v-if="isManager" class="review-buttons">
                <el-button
                  type="success"
                  :icon="CircleCheck"
                  :loading="reviewLoading"
                  @click="handleApprove"
                >
                  审核通过
                </el-button>
                <el-button
                  type="danger"
                  :icon="CloseBold"
                  :loading="reviewLoading"
                  @click="handleReject"
                >
                  驳回
                </el-button>
              </div>
              <div v-else class="review-buttons">
                <span class="text-muted">审核中,请等待管理员审核</span>
              </div>
            </template>
            <!-- approved:已通过,不可重复提交 -->
            <template v-else-if="requirement.status === 'approved'">
              <div class="review-hint review-hint-success">
                需求已审核通过,Bid Agent 可读取此需求生成投标文件。
              </div>
            </template>
          </div>
        </el-card>

        <!-- 文本字段 -->
        <el-card class="mb-16" shadow="never">
          <template #header>
            <div class="card-header">
              <el-icon><Document /></el-icon>
              <span>基本信息(文本字段)</span>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item
              v-for="field in textFieldList"
              :key="field.key"
              :label="field.label"
            >
              <span v-if="field.value">{{ field.value }}</span>
              <span v-else class="text-muted">(未提取)</span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 列表字段 -->
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <el-icon><Collection /></el-icon>
              <span>详细要求(列表字段)</span>
            </div>
          </template>
          <div class="list-fields">
            <el-card
              v-for="field in listFieldList"
              :key="field.key"
              shadow="never"
              class="list-field-card"
            >
              <template #header>
                <div class="list-field-header">
                  <span>{{ field.label }}</span>
                  <el-tag size="small" type="info">{{ field.value?.length || 0 }} 项</el-tag>
                </div>
              </template>
              <ul v-if="field.value && field.value.length" class="list-field-ul">
                <li v-for="(item, idx) in field.value" :key="idx">{{ item }}</li>
              </ul>
              <div v-else class="text-muted">(未提取)</div>
            </el-card>
          </div>
        </el-card>
      </template>

      <el-empty v-else-if="!loading" description="请选择招标文件查看需求解析结果">
        <el-button
          v-if="bidOptions.length === 0"
          type="primary"
          :icon="Upload"
          @click="goUpload"
        >
          前往上传招标文件
        </el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup>
/**
 * 需求解析页(Sprint 7 - v0.9.0)
 *
 * 职责:
 * - 选择已解析成功的招标文件
 * - 展示 15 字段 Requirement(文本字段表格 + 列表字段卡片)
 * - 展示质量指标(字段数 / 缺失数 / 置信度)
 * - 一键跳转生成投标文件
 *
 * 与 BidDetail 的差异:
 * - BidDetail 侧重招标文件本身(含全文 / 文件信息 / 上传者)
 * - 本页侧重需求解析(15 字段 + 质量指标),供业务人员快速浏览多个招标需求
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Document, Collection, MagicStick, Search, Upload,
  Checked, Promotion, CircleCheck, CloseBold,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listBidDocuments, getBidRequirement,
  submitRequirementReview, reviewRequirement,
} from '@/api/bid'
import {
  BID_REQUIREMENT_FIELDS,
  REQUIREMENT_STATUS, REQUIREMENT_STATUS_LABELS, REQUIREMENT_STATUS_TAG_TYPES,
} from '@/utils/constants'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()

const loadingBids = ref(false)
const loading = ref(false)
const bidOptions = ref([])
const selectedBidId = ref(null)
const requirement = ref(null)
const reviewLoading = ref(false)

// 权限:admin / contract_manager 可执行审核操作
const isManager = computed(() => authStore.isManager)

// 需求审核状态标签(基于 requirement.status,修复原 status==='success' 误用 bug)
const statusLabel = computed(
  () => REQUIREMENT_STATUS_LABELS[requirement.value?.status] || requirement.value?.status || '-'
)
const statusTagType = computed(
  () => REQUIREMENT_STATUS_TAG_TYPES[requirement.value?.status] || 'info'
)

// 质量指标卡片样式(基于审核状态:approved=绿 failed=红 其他=默认蓝)
const overviewCardClass = computed(() => {
  const s = requirement.value?.status
  if (s === REQUIREMENT_STATUS.APPROVED) return 'overview-success'
  if (s === REQUIREMENT_STATUS.FAILED) return 'overview-failed'
  return ''
})

// 审核驳回原因(后端驳回时把 comment 写入 error_message,格式 [审核驳回] xxx)
const rejectComment = computed(() => {
  const s = requirement.value?.status
  const msg = requirement.value?.error_message
  if (s === REQUIREMENT_STATUS.DRAFT && msg && msg.startsWith('[审核驳回]')) {
    return msg.replace('[审核驳回]', '').trim()
  }
  return ''
})

// 是否展示审核操作面板(draft/reviewing/approved 展示;failed/pending 不展示)
const canShowReviewPanel = computed(() => {
  const s = requirement.value?.status
  return [
    REQUIREMENT_STATUS.DRAFT,
    REQUIREMENT_STATUS.REVIEWING,
    REQUIREMENT_STATUS.APPROVED,
  ].includes(s)
})

const textFieldList = computed(() => {
  const data = requirement.value?.requirement_data || {}
  return BID_REQUIREMENT_FIELDS
    .filter((f) => f.type === 'text')
    .map((f) => ({ ...f, value: data[f.key] }))
})

const listFieldList = computed(() => {
  const data = requirement.value?.requirement_data || {}
  return BID_REQUIREMENT_FIELDS
    .filter((f) => f.type === 'list')
    .map((f) => ({ ...f, value: data[f.key] }))
})

async function fetchBids() {
  loadingBids.value = true
  try {
    // 仅展示已解析成功的招标文件
    const res = await listBidDocuments({ page: 1, size: 100, status: 'success' })
    bidOptions.value = res.data.items || []
  } catch (e) {
    bidOptions.value = []
  } finally {
    loadingBids.value = false
  }
}

async function handleBidChange(bidId) {
  if (!bidId) {
    requirement.value = null
    return
  }
  loading.value = true
  try {
    const res = await getBidRequirement(bidId)
    requirement.value = res.data
  } catch (e) {
    requirement.value = null
  } finally {
    loading.value = false
  }
}

// ---------- 需求审核流操作(Sprint 7.1 - v0.9.1) ----------
// draft → reviewing → approved / draft(驳回)
// 异常处理:request.js 已统一捕获并 ElMessage.error,catch 仅阻止 loading 残留

async function refreshRequirement() {
  if (!selectedBidId.value) return
  try {
    const res = await getBidRequirement(selectedBidId.value)
    requirement.value = res.data
  } catch (e) {
    // 刷新失败保持原状态(request.js 已提示错误)
  }
}

async function handleSubmitReview() {
  if (!selectedBidId.value) return
  reviewLoading.value = true
  try {
    const res = await submitRequirementReview(selectedBidId.value)
    requirement.value = res.data
    ElMessage.success('已提交审核,等待管理员审核')
  } catch (e) {
    // 状态冲突 / 网络异常 由 request.js 统一提示
  } finally {
    reviewLoading.value = false
  }
}

async function handleApprove() {
  if (!selectedBidId.value) return
  reviewLoading.value = true
  try {
    const res = await reviewRequirement(selectedBidId.value, true)
    requirement.value = res.data
    ElMessage.success('审核已通过,可生成投标文件')
  } catch (e) {
    // request.js 已统一提示
  } finally {
    reviewLoading.value = false
  }
}

async function handleReject() {
  if (!selectedBidId.value) return
  // 弹窗输入驳回原因(必填,1-500 字)
  try {
    const { value: comment } = await ElMessageBox.prompt(
      '请输入驳回原因(审核意见)',
      '驳回需求',
      {
        confirmButtonText: '确认驳回',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '请填写驳回原因,将展示给需求提交者',
        inputValidator: (val) => {
          if (!val || !val.trim()) return '驳回原因不能为空'
          if (val.length > 500) return '驳回原因不能超过 500 字'
          return true
        },
      }
    )
    reviewLoading.value = true
    const res = await reviewRequirement(selectedBidId.value, false, comment.trim())
    requirement.value = res.data
    ElMessage.success('已驳回,需求回到草稿状态')
  } catch (e) {
    // ElMessageBox 取消 throw 'cancel'/'close',忽略;API 错误由 request.js 提示
  } finally {
    reviewLoading.value = false
  }
}

function goGenerate() {
  if (selectedBidId.value) {
    router.push(`/proposals/create?bid_document_id=${selectedBidId.value}`)
  }
}

function goUpload() {
  router.push('/bids/upload')
}

onMounted(() => {
  fetchBids()
})
</script>

<style scoped>
.page-container { padding: 0; }
.filter-card { border: 1px solid #ebeef5; }
.mb-16 { margin-bottom: 16px; }
.mt-12 { margin-top: 12px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-form { margin: 0; }

/* 状态总览 */
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
  align-items: center;
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
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}
.stat-value-small {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
  font-family: monospace;
}
.stat-value.info { color: #409eff; }
.stat-value.warning { color: #e6a23c; }
.stat-value.danger { color: #f56c6c; }

/* 列表字段 */
.list-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 12px;
}
.list-field-card {
  background: #fafafa;
}
.list-field-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.list-field-ul {
  margin: 0;
  padding-left: 20px;
  color: #303133;
  font-size: 13px;
  line-height: 1.8;
}

.text-muted { color: #909399; font-size: 12px; font-style: italic; }

/* 需求审核卡片(Sprint 7.1) */
.review-card {
  border-left: 4px solid #e6a23c;
}
.ml-8 { margin-left: 8px; }
.review-version {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
  font-family: monospace;
}
.review-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.review-hint {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.review-hint-success {
  color: #67c23a;
  font-weight: 500;
}
.review-buttons {
  display: flex;
  gap: 12px;
  align-items: center;
}
</style>
