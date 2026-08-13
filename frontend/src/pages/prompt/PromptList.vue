<template>
  <!-- Prompt 管理中心:列表 / 筛选 / CRUD / 激活 / 查看 -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="Prompt 名称">
          <el-select
            v-model="filterForm.name"
            placeholder="全部"
            clearable
            style="width: 200px"
          >
            <el-option
              v-for="(label, key) in PROMPT_NAME_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filterForm.status"
            placeholder="全部"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="(label, key) in PROMPT_STATUS_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">
            搜索
          </el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
          <el-button :icon="RefreshRight" @click="loadList">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>
            Prompt 管理
            <span class="legend">绿色高亮行 = 当前生效版本(active)</span>
          </span>
          <el-button
            v-if="isAdmin"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新建 Prompt
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        border
        :empty-text="emptyText"
        :row-class-name="rowClassName"
        style="width: 100%"
      >
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <span>{{ PROMPT_NAME_LABELS[row.name] || row.name }}</span>
            <div class="name-raw">{{ row.name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="版本" prop="version" width="100" align="center" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag
              :type="statusTagType(row.status)"
              effect="dark"
              size="small"
            >
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="描述" prop="description" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.description">{{ row.description }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建人" width="120">
          <template #default="{ row }">
            {{ row.created_by_username || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.updated_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              link
              :icon="View"
              @click="openView(row)"
            >
              查看
            </el-button>
            <el-button
              v-if="isAdmin"
              type="primary"
              size="small"
              link
              :icon="Edit"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="isAdmin && row.status !== PROMPT_STATUS.ACTIVE"
              type="success"
              size="small"
              link
              :icon="CircleCheck"
              @click="handleActivate(row)"
            >
              激活
            </el-button>
            <el-button
              v-if="isAdmin && row.status !== PROMPT_STATUS.ACTIVE"
              type="danger"
              size="small"
              link
              :icon="Delete"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 创建 / 编辑对话框 -->
    <el-dialog
      v-model="formVisible"
      :title="formMode === 'create' ? '新建 Prompt' : '编辑 Prompt'"
      width="70%"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="120px"
      >
        <el-form-item label="Prompt 名称" prop="name">
          <el-select
            v-model="formData.name"
            :disabled="formMode === 'edit'"
            placeholder="请选择 Prompt 名称"
            style="width: 100%"
          >
            <el-option
              v-for="(label, key) in PROMPT_NAME_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
          <div class="form-hint">name 创建后不可修改;后端仅允许 6 种合法名称</div>
        </el-form-item>
        <el-form-item label="版本" prop="version">
          <el-input v-model="formData.version" placeholder="如 v1.1" maxlength="32" />
          <div class="form-hint">同一 name 不允许重复 version</div>
        </el-form-item>
        <el-form-item label="System Prompt" prop="system_prompt">
          <el-input
            v-model="formData.system_prompt"
            type="textarea"
            :rows="8"
            placeholder="系统提示词(定义 Agent 角色与输出约束)"
          />
        </el-form-item>
        <el-form-item label="Human Prompt" prop="human_prompt">
          <el-input
            v-model="formData.human_prompt"
            type="textarea"
            :rows="6"
            placeholder="用户提示词模板(可含 {{变量}} 占位符)"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
            placeholder="可选,描述本版本用途"
          />
        </el-form-item>
        <el-form-item v-if="formMode === 'create'">
          <div class="form-hint">
            新建模板默认状态为「草稿(draft)」,不影响现有生效版本。创建后可通过「激活」操作切换为生效。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 查看详情对话框 -->
    <el-dialog
      v-model="viewVisible"
      title="Prompt 详情"
      width="75%"
      destroy-on-close
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item label="名称">
          {{ PROMPT_NAME_LABELS[viewData.name] || viewData.name }}
        </el-descriptions-item>
        <el-descriptions-item label="版本">{{ viewData.version }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTagType(viewData.status)" size="small">
            {{ statusLabel(viewData.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建人">
          {{ viewData.created_by_username || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatTime(viewData.created_time) }}
        </el-descriptions-item>
        <el-descriptions-item label="更新时间">
          {{ formatTime(viewData.updated_time) }}
        </el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">
          {{ viewData.description || '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="prompt-section">
        <div class="prompt-section-title">System Prompt</div>
        <pre class="prompt-pre">{{ viewData.system_prompt }}</pre>
      </div>
      <div class="prompt-section">
        <div class="prompt-section-title">Human Prompt</div>
        <pre class="prompt-pre">{{ viewData.human_prompt }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * Prompt 管理中心(Sprint 8 - v1.0.0)
 *
 * 职责:
 * - 分页查询 Prompt 模板(支持 name / status 筛选)
 * - 新建 / 编辑 / 激活 / 删除 Prompt 模板
 * - 查看详情(System Prompt / Human Prompt 全文,支持长文本滚动)
 * - 直观展示「当前生效版本」:active 行绿色高亮
 *
 * 解决的历史问题:
 * - 此前 contract_review 测试 Prompt 被误设为 active,覆盖正式 .md Prompt,
 *   导致 Agent LLM 输出结构异常。本页面让管理员通过 UI 管理 Prompt,
 *   避免直接操作数据库造成脏数据。
 *
 * 权限(与后端 role_required 对齐):
 * - 列表 / 详情查看:admin / contract_manager(isManager)
 * - 新建 / 编辑 / 激活 / 删除:仅 admin(isAdmin)
 * - employee:菜单不可见 + 路由守卫拦截(meta.roles)
 *
 * 状态机:
 * - draft(草稿) → active(激活,同 name 其他自动 inactive)
 * - active → inactive(通过激活其他版本间接实现)
 * - active 模板禁止直接删除,需先激活其他版本
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Refresh, RefreshRight, Plus, View, Edit, Delete, CircleCheck,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import {
  listPromptTemplates, getPromptTemplate, createPromptTemplate,
  updatePromptTemplate, activatePromptTemplate, deletePromptTemplate,
} from '@/api/prompt'
import {
  PROMPT_STATUS, PROMPT_STATUS_LABELS, PROMPT_STATUS_TAG_TYPES,
  PROMPT_NAME_LABELS,
} from '@/utils/constants'
import { formatTime } from '@/utils/format'

const authStore = useAuthStore()

// 权限:admin 可完整管理;contract_manager 仅查看;employee 不可见菜单 + 路由拦截
const isAdmin = computed(() => authStore.isAdmin)

// ---------- 筛选 ----------
const filterForm = reactive({
  name: '',
  status: '',
})

// ---------- 分页 ----------
const pagination = reactive({
  page: 1,
  size: 20,
  total: 0,
})

// ---------- 表格 ----------
const loading = ref(false)
const tableData = ref([])

const emptyText = computed(() => {
  const hasFilter = filterForm.name || filterForm.status
  return hasFilter ? '未找到匹配的 Prompt 模板,请调整筛选条件' : '暂无 Prompt 模板,请新建'
})

// 状态展示工具(供模板多次调用)
function statusLabel(s) {
  return PROMPT_STATUS_LABELS[s] || s || '-'
}
function statusTagType(s) {
  return PROMPT_STATUS_TAG_TYPES[s] || 'info'
}

// active 行高亮:直观识别「当前生效版本」
function rowClassName({ row }) {
  return row.status === PROMPT_STATUS.ACTIVE ? 'row-active' : ''
}

async function loadList() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      size: pagination.size,
    }
    if (filterForm.name) params.name = filterForm.name
    if (filterForm.status) params.status = filterForm.status

    const res = await listPromptTemplates(params)
    tableData.value = res.data.items || []
    pagination.total = res.data.total || 0
  } catch (e) {
    tableData.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadList()
}

function handleReset() {
  filterForm.name = ''
  filterForm.status = ''
  pagination.page = 1
  loadList()
}

function handleSizeChange(size) {
  pagination.size = size
  pagination.page = 1
  loadList()
}

function handlePageChange(page) {
  pagination.page = page
  loadList()
}

// ---------- 创建 / 编辑 ----------
const formVisible = ref(false)
const formMode = ref('create') // 'create' | 'edit'
const submitting = ref(false)
const formRef = ref(null)
const formData = reactive({
  id: null,
  name: '',
  version: '',
  system_prompt: '',
  human_prompt: '',
  description: '',
})

const formRules = {
  name: [{ required: true, message: '请选择 Prompt 名称', trigger: 'change' }],
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
  system_prompt: [{ required: true, message: 'System Prompt 不能为空', trigger: 'blur' }],
  human_prompt: [{ required: true, message: 'Human Prompt 不能为空', trigger: 'blur' }],
}

function resetForm() {
  formData.id = null
  formData.name = ''
  formData.version = ''
  formData.system_prompt = ''
  formData.human_prompt = ''
  formData.description = ''
}

function openCreate() {
  formMode.value = 'create'
  resetForm()
  formVisible.value = true
}

async function openEdit(row) {
  formMode.value = 'edit'
  // 拉取详情确保拿到完整 system_prompt / human_prompt 全文
  try {
    const res = await getPromptTemplate(row.id)
    const d = res.data
    formData.id = d.id
    formData.name = d.name
    formData.version = d.version
    formData.system_prompt = d.system_prompt || ''
    formData.human_prompt = d.human_prompt || ''
    formData.description = d.description || ''
    formVisible.value = true
  } catch (e) {
    // 拦截器已提示
  }
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        version: formData.version,
        system_prompt: formData.system_prompt,
        human_prompt: formData.human_prompt,
        description: formData.description || null,
      }
      if (formMode.value === 'create') {
        payload.name = formData.name
        await createPromptTemplate(payload)
        ElMessage.success('创建成功')
      } else {
        await updatePromptTemplate(formData.id, payload)
        ElMessage.success('更新成功')
      }
      formVisible.value = false
      loadList()
    } catch (e) {
      // 后端校验错误(如 version 冲突)由拦截器统一提示
    } finally {
      submitting.value = false
    }
  })
}

// ---------- 激活(本页面核心功能) ----------
// 调用 POST /prompts/{id}/activate,后端事务保证同 name 其他版本自动 inactive
async function handleActivate(row) {
  try {
    await ElMessageBox.confirm(
      `激活该 Prompt 后,同名其他版本将自动失效,确定继续吗?\n\n` +
      `名称:${PROMPT_NAME_LABELS[row.name] || row.name}\n` +
      `版本:${row.version}`,
      '激活确认',
      {
        confirmButtonText: '确定激活',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return // 用户取消
  }
  try {
    await activatePromptTemplate(row.id)
    ElMessage.success('激活成功,同名其他版本已自动停用')
    loadList()
  } catch (e) {
    // 拦截器已提示
  }
}

// ---------- 删除 ----------
// active 状态模板后端禁止直接删除,前端仅对非 active 显示删除按钮;
// 若并发场景下后端拒绝,正常展示后端错误,不绕过限制
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `删除后无法恢复,确定删除吗?\n\n` +
      `名称:${PROMPT_NAME_LABELS[row.name] || row.name}\n` +
      `版本:${row.version}`,
      '删除确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }
  try {
    await deletePromptTemplate(row.id)
    ElMessage.success('删除成功')
    // 若当前页只剩一条且非首页,回退一页
    if (tableData.value.length === 1 && pagination.page > 1) {
      pagination.page -= 1
    }
    loadList()
  } catch (e) {
    // 拦截器已提示(如 active 模板删除被后端拒绝)
  }
}

// ---------- 查看详情 ----------
const viewVisible = ref(false)
const viewData = ref({})
async function openView(row) {
  try {
    const res = await getPromptTemplate(row.id)
    viewData.value = res.data
    viewVisible.value = true
  } catch (e) {
    // 拦截器已提示
  }
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.page-container { padding: 0; }

.filter-card {
  background-color: #fff;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.legend {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
  font-weight: normal;
}

.name-raw {
  font-size: 11px;
  color: #909399;
  font-family: monospace;
  margin-top: 2px;
}

.text-muted {
  color: #909399;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* active 行绿色高亮:直观识别当前生效版本 */
:deep(.el-table .row-active td.el-table__cell) {
  background-color: rgba(103, 194, 58, 0.10) !important;
}

/* 详情对话框:Prompt 长文本展示 */
.prompt-section {
  margin-top: 16px;
}

.prompt-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}

.prompt-pre {
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #303133;
  margin: 0;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 4px;
}

.mb-16 { margin-bottom: 16px; }
</style>
