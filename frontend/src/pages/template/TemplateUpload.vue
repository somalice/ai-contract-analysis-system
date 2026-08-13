<template>
  <!-- 上传合同模板页:选择 .docx 文件 + 自动解析 {{variable}} 占位符 -->
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>上传合同模板</span>
          <el-button :icon="Back" @click="goBack">返回</el-button>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        style="max-width: 720px"
      >
        <el-form-item label="模板文件" prop="file">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-exceed="handleExceed"
            accept=".docx"
            drag
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              拖拽 .docx 文件到此处,或 <em>点击选择</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                仅支持 .docx 格式;模板中使用 <code>&#123;&#123;variable&#125;&#125;</code> 语法定义占位符,上传后自动解析
              </div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item label="模板名称" prop="name">
          <el-input
            v-model="form.name"
            placeholder="留空则取文件名(去扩展名)"
            maxlength="255"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="合同类型" prop="contract_type">
          <el-input
            v-model="form.contract_type"
            placeholder="如:采购合同 / 销售合同 / 服务合同"
            maxlength="64"
          />
        </el-form-item>

        <el-form-item label="模板版本" prop="version">
          <el-input
            v-model="form.version"
            placeholder="如:v1.0(留空默认 v1.0)"
            maxlength="32"
          />
          <div class="form-tip">
            用于区分同名模板的不同迭代版本,留空时默认 v1.0
          </div>
        </el-form-item>

        <el-form-item label="模板说明" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="模板用途 / 适用场景 / 注意事项(可选)"
            maxlength="5000"
            show-word-limit
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :icon="Upload"
            :loading="submitting"
            @click="handleSubmit"
          >
            上传模板
          </el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 上传成功后展示解析出的变量 -->
      <el-card v-if="resultTemplate" shadow="never" class="result-card">
        <template #header>
          <div class="card-header">
            <span>解析结果</span>
            <el-tag type="success">解析成功</el-tag>
          </div>
        </template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="模板编号">{{ resultTemplate.template_no }}</el-descriptions-item>
          <el-descriptions-item label="模板名称">{{ resultTemplate.name }}</el-descriptions-item>
          <el-descriptions-item label="合同类型">{{ resultTemplate.contract_type }}</el-descriptions-item>
          <el-descriptions-item label="模板版本">
            <el-tag size="small" type="success">{{ resultTemplate.version || 'v1.0' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="变量数量">{{ resultTemplate.variable_count }}</el-descriptions-item>
        </el-descriptions>

        <el-table v-if="resultTemplate.variables?.length" :data="resultTemplate.variables" stripe border style="margin-top: 12px">
          <el-table-column label="变量名" prop="name" min-width="160" />
          <el-table-column label="显示名" prop="label" min-width="160" />
          <el-table-column label="必填" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.required ? 'danger' : 'info'" size="small">
                {{ row.required ? '必填' : '可选' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="示例值" prop="sample" min-width="160" />
        </el-table>

        <div class="actions">
          <el-button type="primary" :icon="View" @click="goDetail">查看模板详情</el-button>
          <el-button :icon="MagicStick" @click="goGenerate">使用此模板生成合同</el-button>
        </div>
      </el-card>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 上传合同模板页(Sprint 6 - v0.8.0)
 *
 * 职责:
 * - 选择 .docx 模板文件
 * - 填写模板名称 / 类型 / 版本 / 描述
 * - 上传后展示解析出的 {{variable}} 变量列表
 */
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Upload, Refresh, Back, View, MagicStick, UploadFilled,
} from '@element-plus/icons-vue'
import { uploadTemplate } from '@/api/template'

const router = useRouter()
const formRef = ref(null)
const uploadRef = ref(null)
const submitting = ref(false)
const resultTemplate = ref(null)

const form = reactive({
  file: null,
  name: '',
  contract_type: '',
  version: '',
  description: '',
})

const rules = {
  file: [{ required: true, message: '请选择 .docx 模板文件', trigger: 'change' }],
}

function handleFileChange(file) {
  if (file) {
    form.file = file.raw
  }
}

function handleExceed() {
  ElMessage.warning('只能上传 1 个文件,请先移除已选文件')
}

async function handleSubmit() {
  if (!form.file) {
    ElMessage.warning('请先选择 .docx 模板文件')
    return
  }
  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('file', form.file)
    if (form.name) fd.append('name', form.name)
    if (form.contract_type) fd.append('contract_type', form.contract_type)
    if (form.version) fd.append('version', form.version)
    if (form.description) fd.append('description', form.description)

    const res = await uploadTemplate(fd)
    resultTemplate.value = res.data.template
    ElMessage.success('模板上传成功,已解析变量')
  } catch (e) {
    // 错误提示由拦截器统一处理
  } finally {
    submitting.value = false
  }
}

function handleReset() {
  form.file = null
  form.name = ''
  form.contract_type = ''
  form.version = ''
  form.description = ''
  resultTemplate.value = null
  uploadRef.value?.clearFiles()
}

function goBack() {
  router.push('/templates')
}

function goDetail() {
  if (resultTemplate.value) {
    router.push(`/templates/${resultTemplate.value.id}`)
  }
}

function goGenerate() {
  if (resultTemplate.value) {
    router.push(`/generation/create?template_id=${resultTemplate.value.id}`)
  }
}
</script>

<style scoped>
.page-container { padding: 0; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
.form-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  margin-top: 4px;
}
</style>
