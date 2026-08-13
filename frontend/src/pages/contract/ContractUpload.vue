<template>
  <!-- 上传合同页:PDF/图片上传 + AI 分析 -->
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>上传合同</span>
          <el-button :icon="Back" @click="router.back()">返回</el-button>
        </div>
      </template>

      <el-form
        ref="uploadFormRef"
        :model="uploadForm"
        :rules="rules"
        label-width="100px"
        class="upload-form"
      >
        <!-- 文件上传区(拖拽) -->
        <el-form-item label="合同文件" prop="file">
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
              将合同文件拖拽到此处,或<em>点击上传</em>
            </div>
            <template #tip>
              <div class="upload-tip">
                支持 PDF / PNG / JPG / JPEG,单文件不超过 10MB
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <!-- 合同类型 -->
        <el-form-item label="合同类型" prop="contract_type">
          <el-input
            v-model="uploadForm.contract_type"
            placeholder='如:采购合同、销售合同、服务合同(可选,默认"未分类")'
            clearable
            maxlength="64"
            show-word-limit
          />
        </el-form-item>

        <!-- 合同标题 -->
        <el-form-item label="合同标题" prop="title">
          <el-input
            v-model="uploadForm.title"
            placeholder="可选,留空则自动取文件名"
            clearable
            maxlength="255"
            show-word-limit
          />
        </el-form-item>

        <!-- 描述 -->
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="uploadForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选,合同备注信息"
            maxlength="500"
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
            上传后合同状态为"待分析"。请在详情页点击"开始分析"触发 AI 字段提取(Sprint 3 Document Pipeline)。
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
            {{ uploading ? '上传中...' : '上传合同' }}
          </el-button>
          <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 上传合同页(Sprint 3 - v0.5.0 调整)
 *
 * 职责:
 * - 选择文件(PDF/图片,<=10MB)
 * - 填写合同类型 / 标题 / 描述(可选)
 * - 调用 uploadContract 真实接口
 * - 上传成功 → 跳转合同详情页(analysis_status=pending,待手动触发分析)
 *
 * Sprint 3 变更:
 * - 上传不再自动触发 AI 分析,合同状态为 'pending'
 * - AI 分析改为在详情页点"开始分析"按钮触发(Document Pipeline)
 * - 上传接口快速返回,不再阻塞等待 AI
 */
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload,
  UploadFilled,
  RefreshLeft,
  Back,
} from '@element-plus/icons-vue'
import { uploadContract } from '@/api/contract'

const router = useRouter()

const uploadFormRef = ref(null)
const uploadRef = ref(null)
const selectedFile = ref(null)
const uploading = ref(false)

const uploadForm = reactive({
  contract_type: '',
  title: '',
  description: '',
})

const rules = {
  // file 校验由 el-upload 控制,无需 form rule
}

// 允许的扩展名(与后端 ALLOWED_EXTENSIONS 一致)
const ALLOWED_EXTS = ['pdf', 'png', 'jpg', 'jpeg']
const MAX_SIZE = 10 * 1024 * 1024 // 10MB

/**
 * 文件选择变更
 */
function handleFileChange(file) {
  if (!file || !file.raw) return
  const filename = file.name
  const ext = filename.split('.').pop().toLowerCase()

  // 类型校验
  if (!ALLOWED_EXTS.includes(ext)) {
    ElMessage.error('文件类型不支持,仅支持 PDF / PNG / JPG / JPEG')
    uploadRef.value?.clearFiles()
    selectedFile.value = null
    return
  }

  // 大小校验
  if (file.raw.size > MAX_SIZE) {
    ElMessage.error('文件大小超过 10MB 限制')
    uploadRef.value?.clearFiles()
    selectedFile.value = null
    return
  }

  selectedFile.value = file.raw
}

/**
 * 超出文件数量限制
 */
function handleExceed() {
  ElMessage.warning('一次只能上传一个文件,请先移除已选文件')
}

/**
 * 移除文件
 */
function handleFileRemove() {
  selectedFile.value = null
}

/**
 * 提交上传
 */
async function handleSubmit() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择合同文件')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    if (uploadForm.contract_type) {
      formData.append('contract_type', uploadForm.contract_type)
    }
    if (uploadForm.title) {
      formData.append('title', uploadForm.title)
    }
    if (uploadForm.description) {
      formData.append('description', uploadForm.description)
    }

    const res = await uploadContract(formData)
    const contract = res.data.contract
    ElMessage.success('合同上传成功,请在详情页点击"开始分析"进行 AI 解析')

    // 跳转详情页(analysis_status=pending,等待用户触发分析)
    router.push(`/contracts/${contract.id}`)
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示
    // 上传失败时保留表单内容,允许用户重试
  } finally {
    uploading.value = false
  }
}

/**
 * 重置表单
 */
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
  uploadForm.contract_type = ''
  uploadForm.title = ''
  uploadForm.description = ''
  uploadRef.value?.clearFiles()
  selectedFile.value = null
  ElMessage.success('已重置')
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
</style>
