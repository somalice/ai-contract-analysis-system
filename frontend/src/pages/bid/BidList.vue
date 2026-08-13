<template>
  <!-- 招标文件列表页:分页 / 状态过滤 / 关键字搜索 / 上传 / 详情 / 删除 / 生成投标 -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="关键字">
          <el-input
            v-model="filterForm.keyword"
            placeholder="标题 / 招标编号"
            clearable
            style="width: 220px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="解析状态">
          <el-select
            v-model="filterForm.status"
            placeholder="全部"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="(label, key) in BID_PARSE_STATUS_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>招标文件</span>
          <el-button type="primary" :icon="Upload" @click="goUpload">上传招标文件</el-button>
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
        <el-table-column label="招标编号" prop="bid_no" min-width="220" show-overflow-tooltip />
        <el-table-column label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="handleViewDetail(row)">{{ row.title }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="项目名称" min-width="180" show-overflow-tooltip>
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
        <el-table-column label="截止时间" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.requirement?.deadline">{{ row.requirement.deadline }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="解析状态" width="110">
          <template #default="{ row }">
            <el-tag :type="BID_PARSE_STATUS_TAG_TYPES[row.parse_status] || 'info'" size="small">
              {{ BID_PARSE_STATUS_LABELS[row.parse_status] || row.parse_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上传者" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.uploader">{{ row.uploader.username }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link :icon="View" @click="handleViewDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="row.parse_status === 'success'"
              type="success"
              size="small"
              link
              :icon="MagicStick"
              @click="goGenerate(row)"
            >
              生成投标
            </el-button>
            <el-button
              v-if="row.parse_status === 'failed'"
              type="warning"
              size="small"
              link
              :icon="Refresh"
              @click="handleReparse(row)"
            >
              重新解析
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
 * 招标文件列表页(Sprint 7 - v0.9.0)
 *
 * 职责:
 * - 招标文件分页列表(关键字 / 解析状态过滤)
 * - admin/contract_manager 可见全部招标文件;employee 仅可见自己上传的
 * - 上传 / 详情 / 重新解析 / 生成投标 / 删除
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Refresh, Upload, View, MagicStick, Delete,
} from '@element-plus/icons-vue'
import { listBidDocuments, deleteBidDocument, parseBidDocument } from '@/api/bid'
import { useAuthStore } from '@/store/auth'
import {
  BID_PARSE_STATUS_LABELS, BID_PARSE_STATUS_TAG_TYPES,
} from '@/utils/constants'
import { formatTime } from '@/utils/format'

const router = useRouter()
const authStore = useAuthStore()
const isManager = computed(() => authStore.isManager)

const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const emptyText = ref('暂无招标文件')

const filterForm = reactive({
  keyword: '',
  status: '',
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
    const res = await listBidDocuments(params)
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
    emptyText.value = '暂无招标文件'
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
  filterForm.page = 1
  fetchList()
}

function goUpload() {
  router.push('/bids/upload')
}

function handleViewDetail(row) {
  router.push(`/bids/${row.id}`)
}

function goGenerate(row) {
  router.push(`/proposals/create?bid_document_id=${row.id}`)
}

async function handleReparse(row) {
  try {
    await ElMessageBox.confirm(
      `确定要重新解析招标文件"${row.title}"吗?将重新执行 Pipeline 并覆盖原需求。`,
      '提示',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await parseBidDocument(row.id)
    if (res.data.parse_status === 'success') {
      ElMessage.success('招标文件解析完成')
    } else {
      ElMessage.warning('招标文件解析失败,请稍后重试')
    }
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
      `确定要删除招标文件"${row.title}"吗?关联的需求与生成记录将一并删除,该操作不可恢复。`,
      '危险操作',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'error' }
    )
    await deleteBidDocument(row.id)
    ElMessage.success('招标文件已删除')
    fetchList()
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      // 错误提示由拦截器统一处理
    }
  }
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
.text-muted { color: #909399; font-size: 12px; }
</style>
