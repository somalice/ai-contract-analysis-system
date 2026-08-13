<template>
  <!-- 合同生成页:选择模板 → 填写变量 → 预览 / 生成 -->
  <div class="page-container">
    <!-- 步骤条 -->
    <el-card class="mb-16" shadow="never">
      <el-steps :active="activeStep" align-center>
        <el-step title="选择模板" description="从模板中心选择 .docx 模板" />
        <el-step title="填写变量" description="填写模板占位符变量" />
        <el-step title="预览 / 生成" description="Agent 补充条款 + 渲染 Word" />
      </el-steps>
    </el-card>

    <!-- 步骤 1:选择模板 -->
    <el-card v-if="activeStep === 0" shadow="never">
      <template #header>
        <div class="card-header">
          <span>选择模板</span>
          <el-button :icon="Back" @click="goBack">返回</el-button>
        </div>
      </template>
      <el-form :inline="true" class="filter-form">
        <el-form-item label="关键字">
          <el-input
            v-model="templateFilter.keyword"
            placeholder="模板名称 / 编号"
            clearable
            style="width: 220px"
            @keyup.enter="fetchTemplates"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="fetchTemplates">搜索</el-button>
        </el-form-item>
      </el-form>
      <el-table
        v-loading="loadingTemplates"
        :data="templateList"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column label="模板编号" prop="template_no" min-width="200" show-overflow-tooltip />
        <el-table-column label="模板名称" prop="name" min-width="180" show-overflow-tooltip />
        <el-table-column label="合同类型" prop="contract_type" width="130" show-overflow-tooltip />
        <el-table-column label="版本" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="success">{{ row.version || 'v1.0' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="变量数" prop="variable_count" width="90" align="center" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link :icon="Check" @click="selectTemplate(row)">
              选择
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="templateFilter.page"
          v-model:page-size="templateFilter.size"
          :total="templateTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, prev, pager, next"
          background
          @size-change="fetchTemplates"
          @current-change="fetchTemplates"
        />
      </div>
    </el-card>

    <!-- 步骤 2:填写变量 -->
    <el-card v-if="activeStep === 1" shadow="never">
      <template #header>
        <div class="card-header">
          <span>填写变量 — {{ selectedTemplate?.name }}</span>
          <div>
            <el-button :icon="Back" @click="activeStep = 0">上一步</el-button>
          </div>
        </div>
      </template>
      <el-form ref="varFormRef" :model="varForm" label-width="160px" style="max-width: 720px">
        <el-form-item v-if="!selectedTemplate?.variables?.length">
          <el-alert type="info" :closable="false" show-icon>
            该模板未解析到变量,可直接进入下一步生成。
          </el-alert>
        </el-form-item>
        <el-form-item
          v-for="v in selectedTemplate?.variables || []"
          :key="v.name"
          :label="v.label || v.name"
          :required="v.required"
        >
          <el-input
            v-model="varForm[v.name]"
            :placeholder="v.sample ? `示例:${v.sample}` : `请输入 ${v.name}`"
            clearable
          />
          <div v-if="v.sample" class="field-tip">示例值:{{ v.sample }}</div>
        </el-form-item>

        <el-divider content-position="left">合同信息(可选)</el-divider>
        <el-form-item label="合同标题">
          <el-input
            v-model="extraForm.title"
            placeholder="留空则取模板名 + 日期"
            maxlength="255"
          />
        </el-form-item>
        <el-form-item label="合同类型">
          <el-input
            v-model="extraForm.contract_type"
            :placeholder="selectedTemplate?.contract_type || '未分类'"
            maxlength="64"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="extraForm.description"
            type="textarea"
            :rows="2"
            placeholder="可选"
            maxlength="5000"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :icon="ArrowRight" @click="goPreviewStep">
            下一步:预览 / 生成
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 步骤 3:预览 / 生成 -->
    <el-card v-if="activeStep === 2" shadow="never" v-loading="generating" element-loading-text="Agent 正在生成,请稍候...">
      <template #header>
        <div class="card-header">
          <span>预览 / 生成</span>
          <div>
            <el-button :icon="Back" @click="activeStep = 1">上一步</el-button>
          </div>
        </div>
      </template>

      <!-- 操作按钮 -->
      <div class="actions-bar">
        <el-button
          type="warning"
          :icon="View"
          :loading="generating"
          :disabled="!!generatedResult"
          @click="handlePreview"
        >
          预览生成结果(不渲染 Word)
        </el-button>
        <el-button
          type="primary"
          :icon="MagicStick"
          :loading="generating"
          :disabled="!!generatedResult"
          @click="handleGenerate"
        >
          正式生成合同(渲染 Word + 建合同)
        </el-button>
      </div>

      <!-- 生成结果展示 -->
      <template v-if="generatedResult">
        <el-alert
          :title="resultAlertTitle"
          :type="generatedResult.generation.status === 'success' ? 'success' : 'error'"
          :description="generatedResult.generation.error_message || generatedResult.generation.llm_error || ''"
          :closable="false"
          show-icon
          class="mb-16"
        />

        <!-- 生成摘要 -->
        <el-card shadow="never" class="section-card">
          <template #header><span>生成摘要</span></template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="生成编号">{{ generatedResult.generation.generation_no }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="GENERATION_STATUS_TAG_TYPES[generatedResult.generation.status]" size="small">
                {{ GENERATION_STATUS_LABELS[generatedResult.generation.status] }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Agent 迭代">{{ generatedResult.generation.iterations }} 次</el-descriptions-item>
            <el-descriptions-item label="补充条款">{{ generatedResult.generation.generated_clauses?.length || 0 }} 条</el-descriptions-item>
            <el-descriptions-item label="RAG 命中">{{ generatedResult.generation.rag_references?.length || 0 }} 条</el-descriptions-item>
            <el-descriptions-item label="校验结果">
              <el-tag
                v-if="generatedResult.generation.validation_results"
                :type="generatedResult.generation.validation_results.passed ? 'success' : 'warning'"
                size="small"
              >
                {{ generatedResult.generation.validation_results.passed ? '校验通过' : '有未通过项' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="generatedResult.contract" label="创建的合同" :span="2">
              <el-link type="primary" @click="goContractDetail(generatedResult.contract.id)">
                {{ generatedResult.contract.title }} ({{ generatedResult.contract.contract_no }})
              </el-link>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- AI 补充条款 -->
        <el-card v-if="generatedResult.generation.generated_clauses?.length" shadow="never" class="section-card">
          <template #header><span>AI 补充条款</span></template>
          <el-collapse>
            <el-collapse-item
              v-for="(c, idx) in generatedResult.generation.generated_clauses"
              :key="idx"
              :title="`第${idx + 1}条 ${c.name} (来源:${c.source === 'ai' ? 'AI 生成' : '知识库'})`"
            >
              <div class="clause-content">{{ c.content }}</div>
              <div v-if="c.references?.length" class="clause-refs">
                <strong>参考来源:</strong>
                <ul>
                  <li v-for="(r, ri) in c.references" :key="ri">
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
          v-if="generatedResult.generation.validation_results && !generatedResult.generation.validation_results.passed"
          shadow="never"
          class="section-card"
        >
          <template #header><span>校验问题</span></template>
          <el-table :data="generatedResult.generation.validation_results.issues" stripe border>
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
            v-if="generatedResult.generation.status === 'success' && generatedResult.contract"
            type="primary"
            :icon="Download"
            @click="handleDownload"
          >
            下载 Word 文档
          </el-button>
          <el-button :icon="View" @click="goGenerationDetail">
            查看生成详情(含 Trace)
          </el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">
            重新生成
          </el-button>
        </div>
      </template>

      <!-- LLM 降级提示 -->
      <el-alert
        v-if="generatedResult?.generation?.llm_error"
        type="warning"
        :closable="false"
        show-icon
        class="mb-16"
      >
        <template #title>
          LLM 不可用({{ generatedResult.generation.llm_error_type || 'unknown' }}),Agent 已降级为规则校验模式(无 AI 补充条款)
        </template>
        <div>{{ generatedResult.generation.llm_error }}</div>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 合同生成页(Sprint 6 - v0.8.0)
 *
 * 三步流程:
 * 1. 选择模板(从模板中心选择启用模板)
 * 2. 填写变量(动态表单,基于模板 variables)
 * 3. 预览 / 生成(调 Agent + Word 渲染)
 *
 * 支持两种模式:
 * - 预览:跑 Agent,不渲染 Word,不建合同(快速验证)
 * - 生成:跑 Agent + 渲染 Word + 建合同(进入合同管理中心)
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Back, Search, Check, ArrowRight, View, MagicStick,
  Download, RefreshLeft,
} from '@element-plus/icons-vue'
import { listTemplates, getTemplateDetail } from '@/api/template'
import { previewGeneration, generateContract, downloadGeneratedContract } from '@/api/generation'
import {
  GENERATION_STATUS_LABELS, GENERATION_STATUS_TAG_TYPES,
} from '@/utils/constants'

const route = useRoute()
const router = useRouter()

const activeStep = ref(0)
const loadingTemplates = ref(false)
const generating = ref(false)
const templateList = ref([])
const templateTotal = ref(0)
const selectedTemplate = ref(null)
const generatedResult = ref(null)

const templateFilter = reactive({
  keyword: '',
  page: 1,
  size: 10,
})

const varForm = reactive({})
const extraForm = reactive({
  title: '',
  contract_type: '',
  description: '',
})

const resultAlertTitle = computed(() => {
  if (!generatedResult.value) return ''
  const g = generatedResult.value.generation
  if (g.status === 'success') {
    return generatedResult.value.contract
      ? '合同生成成功,已自动创建合同记录'
      : '预览生成完成(未渲染 Word,未建合同)'
  }
  return '生成失败'
})

async function fetchTemplates() {
  loadingTemplates.value = true
  try {
    const params = { page: templateFilter.page, size: templateFilter.size, status: 'active' }
    if (templateFilter.keyword) params.keyword = templateFilter.keyword
    const res = await listTemplates(params)
    templateList.value = res.data.items || []
    templateTotal.value = res.data.total || 0
  } catch (e) {
    templateList.value = []
    templateTotal.value = 0
  } finally {
    loadingTemplates.value = false
  }
}

async function selectTemplate(row) {
  try {
    // 获取模板详情(含 variables)
    const res = await getTemplateDetail(row.id)
    selectedTemplate.value = res.data.template
    // 重置变量表单
    Object.keys(varForm).forEach((k) => delete varForm[k])
    ;(selectedTemplate.value.variables || []).forEach((v) => {
      varForm[v.name] = ''
    })
    extraForm.title = ''
    extraForm.contract_type = selectedTemplate.value.contract_type || ''
    extraForm.description = ''
    generatedResult.value = null
    activeStep.value = 1
  } catch (e) {
    // 错误提示由拦截器统一处理
  }
}

function goPreviewStep() {
  // 必填项校验
  const missing = (selectedTemplate.value?.variables || [])
    .filter((v) => v.required && !varForm[v.name]?.toString().trim())
    .map((v) => v.label || v.name)
  if (missing.length) {
    ElMessage.warning(`以下必填变量未填写:${missing.join(', ')}(若仍要继续,可填占位文本)`)
  }
  activeStep.value = 2
}

async function handlePreview() {
  await runGeneration(false)
}

async function handleGenerate() {
  await runGeneration(true)
}

async function runGeneration(isGenerate) {
  if (!selectedTemplate.value) return
  generating.value = true
  generatedResult.value = null
  try {
    const payload = {
      template_id: selectedTemplate.value.id,
      input_variables: { ...varForm },
    }
    if (extraForm.contract_type) payload.contract_type = extraForm.contract_type
    if (isGenerate) {
      if (extraForm.title) payload.title = extraForm.title
      if (extraForm.description) payload.description = extraForm.description
    }
    const res = isGenerate
      ? await generateContract(payload)
      : await previewGeneration(payload)
    generatedResult.value = res.data
    if (isGenerate && res.data.generation.status === 'success') {
      ElMessage.success('合同生成成功,已自动创建合同记录')
    } else if (res.data.generation.status === 'success') {
      ElMessage.success('预览生成完成')
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
  if (!generatedResult.value?.generation?.id) return
  try {
    const res = await downloadGeneratedContract(generatedResult.value.generation.id)
    // res 为 Blob
    const url = window.URL.createObjectURL(res)
    const a = document.createElement('a')
    a.href = url
    a.download = generatedResult.value.contract?.title
      ? `${generatedResult.value.contract.title}.docx`
      : `${generatedResult.value.generation.generation_no}.docx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('文件下载已开始')
  } catch (e) {
    // 错误提示由拦截器统一处理
  }
}

function goContractDetail(id) {
  router.push(`/contracts/${id}`)
}

function goGenerationDetail() {
  if (generatedResult.value?.generation?.id) {
    router.push(`/generation/${generatedResult.value.generation.id}`)
  }
}

function goBack() {
  router.push('/templates')
}

onMounted(async () => {
  await fetchTemplates()
  // 若 URL 携带 template_id,自动选中
  const tid = route.query.template_id
  if (tid) {
    const t = templateList.value.find((x) => x.id === Number(tid))
    if (t) {
      selectTemplate(t)
    } else {
      // 不在首页,直接获取详情
      try {
        const res = await getTemplateDetail(tid)
        selectedTemplate.value = res.data.template
        ;(selectedTemplate.value.variables || []).forEach((v) => {
          varForm[v.name] = ''
        })
        extraForm.contract_type = selectedTemplate.value.contract_type || ''
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
.field-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
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
.clause-content {
  white-space: pre-wrap;
  line-height: 1.7;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
}
.clause-refs {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}
.clause-refs ul {
  margin: 4px 0 0 16px;
  padding: 0;
}
</style>
