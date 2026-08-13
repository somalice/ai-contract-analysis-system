<template>
  <!-- 上传招标文件页:PDF / 图片 + 同步 Pipeline 解析 -->
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>上传招标文件</span>
          <el-button :icon="Back" @click="goBack">返回</el-button>
        </div>
      </template>

      <el-form
        ref="uploadFormRef"
        :model="uploadForm"
        label-width="100px"
        class="upload-form"
      >
        <!-- 文件上传区(拖拽) -->
        <el-form-item label="招标文件" prop="file">
          <el-upload
            ref="uploadRef"
            class="upload-area"
            drag
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-exceed="handleExceed"
            :on-remove="handleFileRemove"
            :before-upload="() => false"
            accept=".pdf,.png,.jpg,.jpeg"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">
              将招标文件拖拽到此处,或<em>点击上传</em>
            </div>
            <template #tip>
              <div class="upload-tip">
                支持 PDF / PNG / JPG / JPEG,单文件不超过 10MB
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <!-- 招标标题 -->
        <el-form-item label="招标标题" prop="title">
          <el-input
            v-model="uploadForm.title"
            placeholder="可选,留空则自动取文件名"
            clearable
            maxlength="255"
            show-word-limit
          />
        </el-form-item>

        <!-- 提示信息 -->
        <el-alert
          class="upload-alert"
          type="info"
          :closable="false"
          show-icon
        >
          <template #title>
            上传后将同步执行 Bid Pipeline(PDF/OCR → 文本清洗 → LLM 提取 15 字段需求),
            耗时 5–30 秒,请耐心等待。解析失败时可在详情页点击"重新解析"。
          </template>
        </el-alert>

        <!-- 操作按钮 -->
        <el-form-item>
          <el-button
            type="primary"
            :icon="Upload"
            :loading="uploading"
            :disabled="!selectedFile"
            @click="handleSubmit"
          >
            {{ uploading ? '上传解析中...' : '上传招标文件' }}
          </el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 上传成功后展示解析概要 -->
      <el-card v-if="resultBid" shadow="never" class="result-card">
        <template #header>
          <div class="card-header">
            <span>解析结果</span>
            <el-tag :type="BID_PARSE_STATUS_TAG_TYPES[resultBid.parse_status] || 'info'">
              {{ BID_PARSE_STATUS_LABELS[resultBid.parse_status] || resultBid.parse_status }}
            </el-tag>
          </div>
        </template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="招标编号">{{ resultBid.bid_no }}</el-descriptions-item>
          <el-descriptions-item label="招标标题">{{ resultBid.title }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ formatFileSize(resultBid.file_info?.size) }}</el-descriptions-item>
          <el-descriptions-item label="页数">{{ resultBid.page_count }}</el-descriptions-item>
          <el-descriptions-item label="提取方法">{{ resultBid.extract_method }}</el-descriptions-item>
          <el-descriptions-item label="文本长度">{{ resultBid.text_length }} 字符</el-descriptions-item>
          <el-descriptions-item v-if="resultBid.requirement?.project_name" label="项目名称">
            {{ resultBid.requirement.project_name }}
          </el-descriptions-item>
          <el-descriptions-item v-if="resultBid.requirement?.budget" label="预算">
            {{ resultBid.requirement.budget }}
          </el-descriptions-item>
          <el-descriptions-item v-if="resultBid.requirement?.deadline" label="截止时间">
            {{ resultBid.requirement.deadline }}
          </el-descriptions-item>
          <el-descriptions-item v-if="resultBid.requirement" label="字段提取">
            {{ resultBid.requirement.field_count }} / 15 字段 · 置信度
            {{ resultBid.requirement.confidence ? (resultBid.requirement.confidence * 100).toFixed(0) + '%' : '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="resultBid.parse_status === 'failed' && resultBid.error_message" class="error-message">
          <el-alert type="error" :closable="false" show-icon>
            <template #title>解析失败:{{ resultBid.error_message }}</template>
          </el-alert>
        </div>

        <div class="actions">
          <el-button type="primary" :icon="View" @click="goDetail">查看招标详情</el-button>
          <el-button
            v-if="resultBid.parse_status === 'success'"
            type="success"
            :icon="MagicStick"
            @click="goGenerate"
          >
            生成投标文件
          </el-button>
        </div>
      </el-card>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 上传招标文件页(Sprint 7 - v0.9.0)
 *
 * 职责:
 * - 选择文件(PDF/图片,<=10MB)
 * - 填写招标标题(可选)
 * - 调用 uploadBidDocument 真实接口(同步执行 Pipeline)
 * - 上传成功 → 展示解析概要(项目名称 / 预算 / 截止时间 / 字段数 / 置信度)
 *
 * 与合同上传的差异:
 * - 招标文件上传同步执行 Pipeline(合同上传为 pending,详情页触发分析)
 * - 解析结果直接展示在当前页,无需跳转
 */
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, UploadFilled, RefreshLeft, Back, View, MagicStick,
} from '@element-plus/icons-vue'
import { uploadBidDocument } from '@/api/bid'
import {
  BID_PARSE_STATUS_LABELS, BID_PARSE_STATUS_TAG_TYPES,
} from '@/utils/constants'
import { formatFileSize } from '@/utils/format'

const router = useRouter()

const uploadFormRef = ref(null)
const uploadRef = ref(null)
const selectedFile = ref(null)
const uploading = ref(false)
const resultBid = ref(null)

const uploadForm = reactive({
  title: '',
})

// 允许的扩展名(与后端 ALLOWED_EXTENSIONS 一致)
const ALLOWED_EXTS = ['pdf', 'png', 'jpg', 'jpeg']
const MAX_SIZE = 10 * 1024 * 1024 // 10MB

function handleFileChange(file) {
  if (!file || !file.raw) return
  const filename = file.name
  const ext = filename.split('.').pop().toLowerCase()

  if (!ALLOWED_EXTS.includes(ext)) {
    ElMessage.error('文件类型不支持,仅支持 PDF / PNG / JPG / JPEG')
    uploadRef.value?.clearFiles()
    selectedFile.value = null
    return
  }

  if (file.raw.size > MAX_SIZE) {
    ElMessage.error('文件大小超过 10MB 限制')
    uploadRef.value?.clearFiles()
    selectedFile.value = null
    return
  }

  selectedFile.value = file.raw
}

function handleExceed() {
  ElMessage.warning('一次只能上传一个文件,请先移除已选文件')
}

function handleFileRemove() {
  selectedFile.value = null
}

async function handleSubmit() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择招标文件')
    return
  }

  uploading.value = true
  resultBid.value = null
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    if (uploadForm.title) {
      formData.append('title', uploadForm.title)
    }

    const res = await uploadBidDocument(formData)
    resultBid.value = res.data
    if (res.data.parse_status === 'success') {
      ElMessage.success('招标文件上传成功,需求解析完成')
    } else {
      ElMessage.warning('招标文件已上传,但需求解析失败,可重新解析')
    }
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示
  } finally {
    uploading.value = false
  }
}

async function handleReset() {
  try {
    await ElMessageBox.confirm('确定要重置表单内容吗?', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  uploadForm.title = ''
  uploadRef.value?.clearFiles()
  selectedFile.value = null
  resultBid.value = null
  ElMessage.success('已重置')
}

function goBack() {
  router.push('/bids')
}

function goDetail() {
  if (resultBid.value) {
    router.push(`/bids/${resultBid.value.id}`)
  }
}

function goGenerate() {
  if (resultBid.value) {
    router.push(`/proposals/create?bid_document_id=${resultBid.value.id}`)
  }
}
</script>

<style scoped>
.page-container { padding: 0; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.upload-form {
  max-width: 720px;
  margin-top: 12px;
}

.upload-area {
  width: 100%;
}

.upload-area :deep(.el-upload-dragger) {
  width: 100%;
  padding: 30px 20px;
}

.upload-icon {
  font-size: 48px;
  color: #c0c4cc;
  margin-bottom: 8px;
}

.upload-text {
  color: #606266;
  font-size: 14px;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}

.upload-alert {
  margin: 0 0 20px 100px;
  max-width: 620px;
}

.result-card {
  margin-top: 16px;
  background: #f9fafb;
}

.actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

.error-message {
  margin-top: 12px;
}
</style>
