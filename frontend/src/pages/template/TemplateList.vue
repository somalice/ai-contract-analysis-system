<template>
  <!-- 合同模板列表页:模板中心 / 关键字搜索 / 状态过滤 / 上传 / 启停 / 删除 -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="关键字">
          <el-input
            v-model="filterForm.keyword"
            placeholder="模板名称 / 编号"
            clearable
            style="width: 220px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item v-if="isManager" label="状态">
          <el-select
            v-model="filterForm.status"
            placeholder="全部"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="(label, key) in TEMPLATE_STATUS_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="合同类型">
          <el-input
            v-model="filterForm.contract_type"
            placeholder="如:采购合同"
            clearable
            style="width: 160px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="版本">
          <el-input
            v-model="filterForm.version"
            placeholder="如:v1.0"
            clearable
            style="width: 130px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">
            搜索
          </el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>模板中心</span>
          <el-button
            v-if="isManager"
            type="primary"
            :icon="Upload"
            @click="goUpload"
          >
            上传模板
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        border
        :empty-text="emptyText"
        style="width: 100%"
      >
        <el-table-column label="模板编号" prop="template_no" min-width="220" show-overflow-tooltip />
        <el-table-column label="模板名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="handleViewDetail(row)">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="合同类型" prop="contract_type" width="130" show-overflow-tooltip />
        <el-table-column label="版本" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="success">{{ row.version || 'v1.0' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="变量数" prop="variable_count" width="90" align="center" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="TEMPLATE_STATUS_TAG_TYPES[row.status] || 'info'" size="small">
              {{ TEMPLATE_STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建者" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.creator">{{ row.creator.username }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link :icon="View" @click="handleViewDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="isManager"
              type="primary"
              size="small"
              link
              :icon="MagicStick"
              @click="goGenerate(row)"
            >
              生成合同
            </el-button>
            <el-button
              v-if="isManager"
              size="small"
              link
              :icon="row.status === 'active' ? CircleClose : CircleCheck"
              @click="handleToggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-if="isManager"
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
          v-model:current-page="filterForm.page"
          v-model:page-size="filterForm.size"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="fetchList"
          @current-change="fetchList"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 合同模板列表页(Sprint 6 - v0.8.0)
 *
 * 职责:
 * - 模板分页列表(关键字 / 状态 / 类型过滤)
 * - admin/contract_manager 可上传 / 启停 / 删除模板
 * - employee 仅可见启用模板,只能查看详情与生成合同
 * - 点击"生成合同"跳转到生成页面
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Refresh, Upload, View, MagicStick,
  CircleClose, CircleCheck, Delete,
} from '@element-plus/icons-vue'
import { listTemplates, updateTemplateStatus, deleteTemplate } from '@/api/template'
import { useAuthStore } from '@/store/auth'
import {
  TEMPLATE_STATUS_LABELS, TEMPLATE_STATUS_TAG_TYPES, TEMPLATE_STATUS,
} from '@/utils/constants'

const router = useRouter()
const authStore = useAuthStore()
const isManager = computed(() => authStore.isManager)

const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const emptyText = ref('暂无模板数据')

const filterForm = reactive({
  keyword: '',
  status: '',
  contract_type: '',
  version: '',
  page: 1,
  size: 20,
})

async function fetchList() {
  loading.value = true
  emptyText.value = '加载中...'
  try {
    const params = { page: filterForm.page, size: filterForm.size }
    if (filterForm.keyword) params.keyword = filterForm.keyword
    if (filterForm.status) params.status = filterForm.status
    if (filterForm.contract_type) params.contract_type = filterForm.contract_type
    if (filterForm.version) params.version = filterForm.version
    const res = await listTemplates(params)
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
    emptyText.value = '暂无模板数据'
  } catch (e) {
    tableData.value = []
    total.value = 0
    emptyText.value = '加载失败'
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  filterForm.page = 1
  fetchList()
}

function handleReset() {
  filterForm.keyword = ''
  filterForm.status = ''
  filterForm.contract_type = ''
  filterForm.version = ''
  filterForm.page = 1
  fetchList()
}

function goUpload() {
  router.push('/templates/upload')
}

function handleViewDetail(row) {
  router.push(`/templates/${row.id}`)
}

function goGenerate(row) {
  router.push(`/generation/create?template_id=${row.id}`)
}

async function handleToggleStatus(row) {
  const target = row.status === TEMPLATE_STATUS.ACTIVE
    ? TEMPLATE_STATUS.DISABLED
    : TEMPLATE_STATUS.ACTIVE
  const action = target === TEMPLATE_STATUS.ACTIVE ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(
      `确定要${action}模板"${row.name}"吗?`,
      '提示',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await updateTemplateStatus(row.id, target)
    ElMessage.success(`已${action}模板`)
    fetchList()
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      // 错误提示由拦截器统一处理
    }
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除模板"${row.name}"吗?该操作不可恢复(若已有生成记录,将禁止删除,建议改为停用)。`,
      '危险操作',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'error' }
    )
    await deleteTemplate(row.id)
    ElMessage.success('模板已删除')
    fetchList()
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      // 错误提示由拦截器统一处理
    }
  }
}

function formatTime(t) {
  if (!t) return '-'
  return t.replace('T', ' ').split('.')[0]
}

onMounted(() => {
  fetchList()
})
</script>

<style scoped>
.page-container { padding: 0; }
.filter-card { border: 1px solid #ebeef5; }
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
.text-muted { color: #909399; }
</style>
