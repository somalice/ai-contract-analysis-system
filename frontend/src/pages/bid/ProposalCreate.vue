<template>
  <!-- 投标生成页:选择招标文件 → 预览需求 → 生成投标(跑 Agent + Word 渲染) -->
  <div class="page-container">
    <!-- 步骤条 -->
    <el-card class="mb-16" shadow="never">
      <el-steps :active="activeStep" align-center>
        <el-step title="选择招标文件" description="从已解析成功的招标文件中选择" />
        <el-step title="预览需求" description="查看招标需求 15 字段" />
        <el-step title="生成投标" description="Agent 生成章节 + Word 渲染" />
      </el-steps>
    </el-card>

    <!-- 步骤 1:选择招标文件 -->
    <el-card v-if="activeStep === 0" shadow="never">
      <template #header>
        <div class="card-header">
          <span>选择招标文件</span>
          <el-button :icon="Back" @click="goBack">返回</el-button>
        </div>
      </template>
      <el-form :inline="true" class="filter-form">
        <el-form-item label="关键字">
          <el-input
            v-model="bidFilter.keyword"
            placeholder="标题 / 招标编号"
            clearable
            style="width: 220px"
            @keyup.enter="fetchBids"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="fetchBids">搜索</el-button>
        </el-form-item>
      </el-form>
      <el-table
        v-loading="loadingBids"
        :data="bidList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column label="招标编号" prop="bid_no" min-width="220" show-overflow-tooltip />
        <el-table-column label="标题" prop="title" min-width="180" show-overflow-tooltip />
        <el-table-column label="项目名称" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.requirement?.project_name">{{ row.requirement.project_name }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="预算" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.requirement?.budget">{{ row.requirement.budget }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="字段数" width="100" align="center">
          <template #default="{ row }">
            {{ row.requirement?.field_count ?? 0 }} / 15
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link :icon="Check" @click="selectBid(row)">
              选择
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="bidFilter.page"
          v-model:page-size="bidFilter.size"
          :total="bidTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, prev, pager, next"
          background
          @size-change="fetchBids"
          @current-change="fetchBids"
        />
      </div>
    </el-card>

    <!-- 步骤 2:预览需求 -->
    <el-card v-if="activeStep === 1" shadow="never">
      <template #header>
        <div class="card-header">
          <span>预览招标需求 — {{ selectedBid?.title }}</span>
          <div>
            <el-button :icon="Back" @click="activeStep = 0">上一步</el-button>
            <el-button type="primary" :icon="ArrowRight" @click="goGenerateStep">
              下一步:生成投标
            </el-button>
          </div>
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

    <!-- 步骤 3:生成投标 -->
    <el-card v-if="activeStep === 2" shadow="never" v-loading="generating" element-loading-text="Agent 正在生成投标方案,请稍候...">
      <template #header>
        <div class="card-header">
          <span>生成投标</span>
          <div>
            <el-button :icon="Back" @click="activeStep = 1">上一步</el-button>
          </div>
        </div>
      </template>

      <!-- 操作按钮 -->
      <div class="actions-bar">
        <el-button
          type="primary"
          :icon="MagicStick"
          :loading="generating"
          :disabled="!!generatedResult"
          @click="handleGenerate"
        >
          生成投标文件(跑 Agent + Word 渲染)
        </el-button>
      </div>

      <!-- 生成结果展示 -->
      <template v-if="generatedResult">
        <el-alert
          :title="resultAlertTitle"
          :type="generatedResult.proposal.status === 'success' ? 'success' : 'error'"
          :description="generatedResult.proposal.error_message || generatedResult.proposal.llm_error || ''"
          :closable="false"
          show-icon
          class="mb-16"
        />

        <!-- 生成摘要 -->
        <el-card shadow="never" class="section-card">
          <template #header><span>生成摘要</span></template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="生成编号">{{ generatedResult.proposal.proposal_no }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="PROPOSAL_STATUS_TAG_TYPES[generatedResult.proposal.status]" size="small">
                {{ PROPOSAL_STATUS_LABELS[generatedResult.proposal.status] }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Agent 迭代">{{ generatedResult.proposal.iterations }} 次</el-descriptions-item>
            <el-descriptions-item label="生成章节">{{ generatedResult.proposal.generated_sections?.length || 0 }} 章节</el-descriptions-item>
            <el-descriptions-item label="RAG 命中">{{ generatedResult.proposal.rag_references?.length || 0 }} 条</el-descriptions-item>
            <el-descriptions-item label="校验结果">
              <el-tag
                v-if="generatedResult.proposal.validation_results"
                :type="generatedResult.proposal.validation_results.passed ? 'success' : 'warning'"
                size="small"
              >
                {{ generatedResult.proposal.validation_results.passed ? '校验通过' : '有未通过项' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- AI 生成章节 -->
        <el-card v-if="generatedResult.proposal.generated_sections?.length" shadow="never" class="section-card">
          <template #header><span>AI 生成章节</span></template>
          <el-collapse>
            <el-collapse-item
              v-for="(s, idx) in generatedResult.proposal.generated_sections"
              :key="idx"
              :title="`${s.section_name || s.section_type} (来源:${s.source === 'ai' ? 'AI 生成' : '规则模板'})`"
            >
              <div class="section-content">{{ s.content }}</div>
              <div v-if="s.references?.length" class="section-refs">
                <strong>参考来源:</strong>
                <ul>
                  <li v-for="(r, ri) in s.references" :key="ri">
                    {{ r.document_title || '未知文档' }}
                    <span v-if="r.page_number"> 第 {{ r.page_number }} 页</span>
                    <span v-if="r.score"> (相似度 {{ (r.score * 100).toFixed(1) }}%)</span>
                  </li>
                </ul>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>

        <!-- 校验问题 -->
        <el-card
          v-if="generatedResult.proposal.validation_results && !generatedResult.proposal.validation_results.passed"
          shadow="never"
          class="section-card"
        >
          <template #header><span>校验问题</span></template>
          <el-table :data="generatedResult.proposal.validation_results.issues" stripe border>
            <el-table-column label="类型" prop="type" width="160" />
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

        <!-- 操作 -->
        <div class="actions-bar">
          <el-button
            v-if="generatedResult.proposal.status === 'success'"
            type="primary"
            :icon="Download"
            @click="handleDownload"
          >
            下载 Word 文档
          </el-button>
          <el-button :icon="View" @click="goProposalDetail">
            查看生成详情(含 Trace)
          </el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">
            重新生成
          </el-button>
        </div>
      </template>

      <!-- LLM 降级提示 -->
      <el-alert
        v-if="generatedResult?.proposal?.llm_error"
        type="warning"
        :closable="false"
        show-icon
        class="mb-16"
      >
        <template #title>
          LLM 不可用({{ generatedResult.proposal.llm_error_type || 'unknown' }}),Agent 已降级为规则模板模式(无 AI 章节生成)
        </template>
        <div>{{ generatedResult.proposal.llm_error }}</div>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 投标生成页(Sprint 7 - v0.9.0)
 *
 * 三步流程:
 * 1. 选择招标文件(从已解析成功的招标文件中选择)
 * 2. 预览需求(查看 15 字段,确认信息完整)
 * 3. 生成投标(调 Proposal Agent + Word 渲染)
 *
 * 与合同生成的差异:
 * - 不需要填写变量(招标需求自动从 BidRequirement 提取)
 * - 不创建新合同,只生成 Word 投标文件 + 落库 GeneratedProposal
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Back, Search, Check, ArrowRight, View, MagicStick,
  Download, RefreshLeft,
} from '@element-plus/icons-vue'
import { listBidDocuments, getBidRequirement, generateProposal, downloadProposal } from '@/api/bid'
import {
  PROPOSAL_STATUS_LABELS, PROPOSAL_STATUS_TAG_TYPES,
  BID_REQUIREMENT_FIELDS,
} from '@/utils/constants'

const route = useRoute()
const router = useRouter()

const activeStep = ref(0)
const loadingBids = ref(false)
const generating = ref(false)
const bidList = ref([])
const bidTotal = ref(0)
const selectedBid = ref(null)
const requirementData = ref(null)
const generatedResult = ref(null)

const bidFilter = reactive({
  keyword: '',
  page: 1,
  size: 10,
})

const textFieldList = computed(() => {
  const data = requirementData.value?.requirement_data || {}
  return BID_REQUIREMENT_FIELDS
    .filter((f) => f.type === 'text')
    .map((f) => ({ ...f, value: data[f.key] }))
})

const listFieldList = computed(() => {
  const data = requirementData.value?.requirement_data || {}
  return BID_REQUIREMENT_FIELDS
    .filter((f) => f.type === 'list')
    .map((f) => ({ ...f, value: data[f.key] }))
})

const resultAlertTitle = computed(() => {
  if (!generatedResult.value) return ''
  const p = generatedResult.value.proposal
  if (p.status === 'success') {
    return '投标文件生成成功,Word 已渲染'
  }
  return '生成失败'
})

async function fetchBids() {
  loadingBids.value = true
  try {
    const params = { page: bidFilter.page, size: bidFilter.size, status: 'success' }
    if (bidFilter.keyword) params.keyword = bidFilter.keyword
    const res = await listBidDocuments(params)
    bidList.value = res.data.items || []
    bidTotal.value = res.data.total || 0
  } catch (e) {
    bidList.value = []
    bidTotal.value = 0
  } finally {
    loadingBids.value = false
  }
}

async function selectBid(row) {
  try {
    const res = await getBidRequirement(row.id)
    selectedBid.value = row
    requirementData.value = res.data
    generatedResult.value = null
    activeStep.value = 1
  } catch (e) {
    // 错误提示由拦截器统一处理
  }
}

function goGenerateStep() {
  activeStep.value = 2
}

async function handleGenerate() {
  if (!selectedBid.value) return
  generating.value = true
  generatedResult.value = null
  try {
    const res = await generateProposal(selectedBid.value.id)
    generatedResult.value = res.data
    if (res.data.proposal.status === 'success') {
      ElMessage.success('投标文件生成成功,Word 已渲染')
    } else {
      ElMessage.warning('生成任务执行完毕(请查看状态)')
    }
  } catch (e) {
    // 错误提示由拦截器统一处理
  } finally {
    generating.value = false
  }
}

function handleReset() {
  generatedResult.value = null
}

async function handleDownload() {
  if (!generatedResult.value?.proposal?.id) return
  try {
    const res = await downloadProposal(generatedResult.value.proposal.id)
    const url = window.URL.createObjectURL(res)
    const a = document.createElement('a')
    a.href = url
    a.download = generatedResult.value.proposal.file_info?.name
      ? generatedResult.value.proposal.file_info.name
      : `${generatedResult.value.proposal.proposal_no}.docx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('文件下载已开始')
  } catch (e) {
    // 错误提示由拦截器统一处理
  }
}

function goProposalDetail() {
  if (generatedResult.value?.proposal?.id) {
    router.push(`/proposals/${generatedResult.value.proposal.id}`)
  }
}

function goBack() {
  router.push('/bids')
}

onMounted(async () => {
  await fetchBids()
  // 若 URL 携带 bid_document_id,自动选中
  const bidId = route.query.bid_document_id
  if (bidId) {
    const b = bidList.value.find((x) => x.id === Number(bidId))
    if (b) {
      selectBid(b)
    } else {
      // 不在首页,直接获取需求(若已解析成功)
      try {
        const res = await getBidRequirement(bidId)
        selectedBid.value = {
          id: Number(bidId),
          title: res.data.project_name || `招标文件 #${bidId}`,
        }
        requirementData.value = res.data
        activeStep.value = 1
      } catch (e) {
        // 错误提示由拦截器统一处理
      }
    }
  }
})
</script>

<style scoped>
.page-container { padding: 0; }
.mb-16 { margin-bottom: 16px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-form { margin: 0; }
.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.actions-bar {
  display: flex;
  gap: 12px;
  margin: 16px 0;
  flex-wrap: wrap;
}
.section-card {
  margin-top: 16px;
}
.section-content {
  white-space: pre-wrap;
  line-height: 1.7;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}
.section-refs {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}
.section-refs ul {
  margin: 4px 0 0 16px;
  padding: 0;
}
.list-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 12px;
  margin-top: 16px;
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
</style>
