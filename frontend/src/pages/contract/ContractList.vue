<template>
  <!-- 合同列表页:分页 / 关键字搜索 / 状态过滤 / 查看详情 -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="关键字">
          <el-input
            v-model="filterForm.keyword"
            placeholder="合同编号 / 标题"
            clearable
            style="width: 220px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="filterForm.status"
            placeholder="全部"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="(label, key) in STATUS_LABELS"
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
          <span>合同列表</span>
          <el-button
            type="primary"
            :icon="Upload"
            @click="router.push('/contracts/upload')"
          >
            上传合同
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
        <el-table-column label="合同编号" prop="contract_no" min-width="200" show-overflow-tooltip />
        <el-table-column label="标题" prop="title" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" prop="contract_type" width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="180">
          <template #default="{ row }">
            <StatusTag
              :status="row.status"
              :show-analysis="true"
              :analysis-status="row.analysis_status"
            />
          </template>
        </el-table-column>
        <el-table-column label="创建人" width="120">
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
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              link
              :icon="View"
              @click="handleViewDetail(row)"
            >
              查看详情
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
 * 合同列表页
 *
 * 职责:
 * - 调用 listContracts 真实接口获取数据
 * - 支持分页 / 关键字搜索 / 状态过滤
 * - 点击"查看详情"跳转 /contracts/:id
 *
 * 权限:
 * - 后端已对 employee 做数据隔离(仅返回自己的合同),前端无需特殊处理
 * - 列表数据由后端控制,前端仅做展示
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Upload, View } from '@element-plus/icons-vue'
import { listContracts } from '@/api/contract'
import StatusTag from '@/components/contract/StatusTag.vue'
import { STATUS_LABELS } from '@/utils/constants'
import { formatTime } from '@/utils/format'

const router = useRouter()

// ---------- 筛选表单 ----------
const filterForm = reactive({
  keyword: '',
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

/**
 * 空数据提示文案
 * - 有筛选条件时提示"未找到匹配的合同"
 * - 无筛选条件时提示"暂无合同数据"
 */
const emptyText = computed(() => {
  const hasFilter = filterForm.keyword || filterForm.status
  return hasFilter ? '未找到匹配的合同,请调整搜索条件' : '暂无合同数据'
})

/**
 * 加载合同列表
 */
async function loadList() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      size: pagination.size,
    }
    if (filterForm.keyword) params.keyword = filterForm.keyword
    if (filterForm.status) params.status = filterForm.status

    const res = await listContracts(params)
    tableData.value = res.data.items || []
    pagination.total = res.data.total || 0
  } catch (err) {
    // 错误已由 Axios 拦截器统一提示
    tableData.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

/**
 * 搜索(回到第一页)
 */
function handleSearch() {
  pagination.page = 1
  loadList()
}

/**
 * 重置筛选
 */
function handleReset() {
  filterForm.keyword = ''
  filterForm.status = ''
  pagination.page = 1
  loadList()
}

/**
 * 切换每页数量
 */
function handleSizeChange(size) {
  pagination.size = size
  pagination.page = 1
  loadList()
}

/**
 * 切换页码
 */
function handlePageChange(page) {
  pagination.page = page
  loadList()
}

/**
 * 查看详情
 */
function handleViewDetail(row) {
  router.push(`/contracts/${row.id}`)
}

// ---------- 初始化 ----------
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
</style>
