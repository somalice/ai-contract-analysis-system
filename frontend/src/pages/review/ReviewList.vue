<template>
  <!-- 合同审核报告列表页:全局列表 / 风险等级过滤 / 状态过滤 / 查看详情 -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="风险等级">
          <el-select
            v-model="filterForm.risk_level"
            placeholder="全部"
            clearable
            style="width: 150px"
          >
            <el-option
              v-for="(label, key) in RISK_LEVEL_LABELS"
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
              v-for="(label, key) in REVIEW_STATUS_LABELS"
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
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>合同审核</span>
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
        <el-table-column label="审核编号" prop="review_no" min-width="220" show-overflow-tooltip />
        <el-table-column label="关联合同" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.contract">{{ row.contract.title }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.risk_level"
              :type="RISK_LEVEL_TAG_TYPES[row.risk_level] || 'info'"
              effect="dark"
              size="small"
            >
              {{ RISK_LEVEL_LABELS[row.risk_level] || row.risk_level }}
            </el-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="REVIEW_STATUS_TAG_TYPES[row.status] || 'info'" size="small">
              {{ REVIEW_STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="风险数" width="90" align="center">
          <template #default="{ row }">
            <span v-if="row.risks !== null && row.risks !== undefined">
              {{ Array.isArray(row.risks) ? row.risks.length : '-' }}
            </span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="迭代" width="80" align="center">
          <template #default="{ row }">
            {{ row.iterations ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              link
              :icon="View"
              @click="handleViewDetail(row)"
            >
              查看报告
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
  </div>
</template>

<script setup>
/**
 * 合同审核报告列表页(Sprint 5 - v0.7.0)
 *
 * 职责:
 * - 调用 listReviews 获取全局审核报告列表
 * - 支持风险等级 / 状态过滤
 * - 点击"查看报告"跳转 /reviews/:id
 *
 * 权限:
 * - 后端已对 employee 做数据隔离(仅返回自己合同的审核),前端无需特殊处理
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh, View } from '@element-plus/icons-vue'
import { listReviews } from '@/api/review'
import {
  REVIEW_STATUS_LABELS,
  REVIEW_STATUS_TAG_TYPES,
  RISK_LEVEL_LABELS,
  RISK_LEVEL_TAG_TYPES,
} from '@/utils/constants'
import { formatTime } from '@/utils/format'

const router = useRouter()

// ---------- 筛选表单 ----------
const filterForm = reactive({
  risk_level: '',
  status: '',
})

// ---------- 分页 ----------
const pagination = reactive({
  page: 1,
  size: 20,
  total: 0,
})

// ---------- 表格数据 ----------
const loading = ref(false)
const tableData = ref([])

const emptyText = computed(() => {
  const hasFilter = filterForm.risk_level || filterForm.status
  return hasFilter ? '未找到匹配的审核报告,请调整筛选条件' : '暂无审核报告,可在合同详情页触发 AI 风险审核'
})

async function loadList() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      size: pagination.size,
    }
    if (filterForm.risk_level) params.risk_level = filterForm.risk_level
    if (filterForm.status) params.status = filterForm.status

    const res = await listReviews(params)
    tableData.value = res.data.items || []
    pagination.total = res.data.total || 0
  } catch (err) {
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
  filterForm.risk_level = ''
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

function handleViewDetail(row) {
  router.push(`/reviews/${row.id}`)
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
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

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.text-muted {
  color: #c0c4cc;
}
</style>
