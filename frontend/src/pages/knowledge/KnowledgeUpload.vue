<template>
  <!-- 上传知识文档页:PDF/DOCX/TXT → 解析 → Chunk → Embedding → FAISS -->
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>上传知识文档</span>
          <el-button :icon="Back" @click="router.back()">返回</el-button>
        </div>
      </template>

      <el-form
        ref="uploadFormRef"
        :model="uploadForm"
        label-width="100px"
        class="upload-form"
      >
        <!-- 文件上传区(拖拽) -->
        <el-form-item label="知识文档" prop="file">
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
            accept=".pdf,.docx,.txt"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">
              将知识文档拖拽到此处,或<em>点击上传</em>
            </div>
            <template #tip>
              <div class="upload-tip">
                支持 PDF / DOCX / TXT,单文件不超过 10MB
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <!-- 文档标题 -->
        <el-form-item label="文档标题" prop="title">
          <el-input
            v-model="uploadForm.title"
            placeholder="可选,留空则自动取文件名"
            clearable
            maxlength="255"
            show-word-limit
          />
        </el-form-item>

        <!-- 处理流程提示 -->
        <el-alert
          class="upload-alert"
          type="info"
          :closable="false"
          show-icon
        >
          <template #title>
            上传后将同步执行:文档解析 → 语义切分(含 Overlap)→ Embedding(bge-small-zh)→ FAISS 入库。
            首次上传会下载 Embedding 模型,可能耗时较长;后续单文件通常 5–30s。
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
            {{ uploading ? '处理中...' : '上传知识' }}
          </el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 处理结果(成功后展示) -->
      <el-alert
        v-if="resultVisible"
        class="result-alert"
        :type="resultType"
        :closable="false"
        show-icon
      >
        <template #title>
          <div class="result-title">{{ resultTitle }}</div>
        </template>
        <div v-if="resultDocument" class="result-detail">
          <div>文档编号:{{ resultDocument.doc_no }}</div>
          <div>标题:{{ resultDocument.title }}</div>
          <div>
            Embedding 状态:
            <EmbeddingStatusTag
              :status="resultDocument.embedding_status"
              :error-message="resultDocument.error_message"
            />
          </div>
          <div>Chunk 数量:{{ resultDocument.chunk_count }}</div>
          <div v-if="resultDocument.error_message" class="error-msg">
            失败原因:{{ resultDocument.error_message }}
          </div>
        </div>
        <div class="result-actions">
          <el-button type="primary" size="small" @click="goDetail">查看详情</el-button>
          <el-button size="small" @click="goList">返回列表</el-button>
        </div>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 上传知识文档页(Sprint 4 - v0.6.0)
 *
 * 职责:
 * - 选择文件(PDF/DOCX/TXT,<=10MB)
 * - 填写文档标题(可选)
 * - 调用 uploadKnowledgeDocument 真实接口
 * - 上传成功 → 展示结果(Embedding 状态 + Chunk 数);失败 → 展示错误
 *
 * 流程(后端同步):
 *   保存 → 解析 → Chunk 切分 → Embedding → FAISS 入库 → 持久化
 *
 * 容错:
 * - Embedding 失败:文档与 Chunk 已保存,embedding_status=failed(可删除后重新上传)
 * - 解析失败:返回 failed 状态
 */
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload,
  UploadFilled,
  RefreshLeft,
  Back,
} from '@element-plus/icons-vue'
import { uploadKnowledgeDocument } from '@/api/knowledge'
import EmbeddingStatusTag from '@/components/knowledge/EmbeddingStatusTag.vue'
import { EMBEDDING_STATUS } from '@/utils/constants'

const router = useRouter()

const uploadRef = ref(null)
const selectedFile = ref(null)
const uploading = ref(false)

const uploadForm = reactive({
  title: '',
})

// 允许的扩展名(与后端 get_supported_extensions 一致:pdf/docx/txt)
const ALLOWED_EXTS = ['pdf', 'docx', 'txt']
const MAX_SIZE = 10 * 1024 * 1024 // 10MB

// ---------- 结果展示 ----------
const resultVisible = ref(false)
const resultDocument = ref(null)

const resultType = computed(() => {
  if (!resultDocument.value) return 'info'
  return resultDocument.value.embedding_status === EMBEDDING_STATUS.COMPLETED
    ? 'success'
    : 'warning'
})

const resultTitle = computed(() => {
  if (!resultDocument.value) return ''
  return resultDocument.value.embedding_status === EMBEDDING_STATUS.COMPLETED
    ? '上传成功,Embedding 已完成,该文档已可被 RAG 检索'
    : '上传完成,但 Embedding 失败(文档与 Chunk 已保存,但不可检索)'
})

function handleFileChange(file) {
  if (!file || !file.raw) return
  const filename = file.name
  const ext = filename.split('.').pop().toLowerCase()

  if (!ALLOWED_EXTS.includes(ext)) {
    ElMessage.error('文件类型不支持,仅支持 PDF / DOCX / TXT')
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
  // 隐藏上次结果
  resultVisible.value = false
  resultDocument.value = null
}

function handleExceed() {
  ElMessage.warning('一次只能上传一个文件,请先移除已选文件')
}

function handleFileRemove() {
  selectedFile.value = null
}

async function handleSubmit() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择知识文档')
    return
  }

  uploading.value = true
  resultVisible.value = false
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    if (uploadForm.title) {
      formData.append('title', uploadForm.title)
    }

    const res = await uploadKnowledgeDocument(formData)
    resultDocument.value = res.data.document
    resultVisible.value = true

    if (resultDocument.value.embedding_status === EMBEDDING_STATUS.COMPLETED) {
      ElMessage.success('上传成功,Embedding 已完成')
    } else {
      ElMessage.warning('上传完成,但 Embedding 失败,请查看详情')
    }
  } catch (err) {
    // 错误已由拦截器统一提示,保留表单内容供重试
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
  resultVisible.value = false
  resultDocument.value = null
  ElMessage.success('已重置')
}

function goDetail() {
  if (resultDocument.value) {
    router.push(`/knowledge/${resultDocument.value.id}`)
  }
}

function goList() {
  router.push('/knowledge')
}
</script>

<style scoped>
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

.result-alert {
  max-width: 720px;
  margin: 8px 0 0 0;
}

.result-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.result-detail {
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}

.result-detail .error-msg {
  color: #f56c6c;
}

.result-actions {
  margin-top: 10px;
}
</style>
