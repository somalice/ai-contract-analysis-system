<template>
  <!-- 投标文件列表页:分页 / 状态过滤 / 招标文件过滤 / 详情 / 下载 -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="状态">
          <el-select v-model="filterForm.status" placeholder="全部" clearable style="width: 140px">
            <el-option
              v-for="(label, key) in PROPOSAL_STATUS_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="招标文件ID">
          <el-input
            v-model="filterForm.bid_document_id"
            placeholder="可选"
            clearable
            style="width: 120px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>投标文件</span>
          <el-button type="primary" :icon="MagicStick" @click="goCreate">生成新投标</el-button>
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
        <el-table-column label="生成编号" prop="proposal_no" min-width="220" show-overflow-tooltip />
        <el-table-column label="招标文件" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link v-if="row.bid" type="primary" @click="goBid(row.bid.id)">
              {{ row.bid.title }}
            </el-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="PROPOSAL_STATUS_TAG_TYPES[row.status] || 'info'" size="small">
              {{ PROPOSAL_STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="迭代" width="80" align="center">
          <template #default="{ row }">{{ row.iterations ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="章节" width="80" align="center">
          <template #default="{ row }">
            {{ row.generated_sections?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="RAG" width="80" align="center">
          <template #default="{ row }">
            {{ row.rag_references?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link :icon="View" @click="goDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="row.status === 'success'"
              type="success"
              size="small"
              link
              :icon="Download"
              @click="handleDownload(row)"
            >
              下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>

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
 * 投标文件列表页(Sprint 7 - v0.9.0,信息架构重构后菜单名"投标文件")
 *
 * 职责:
 * - 投标生成记录分页(状态 / 招标文件过滤)
 * - admin/contract_manager 可见全部;employee 仅可见自己触发的
 * - 下载已生成的 Word
 */
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Refresh, MagicStick, View, Download } from '@element-plus/icons-vue'
import { listProposals, downloadProposal } from '@/api/bid'
import {
  PROPOSAL_STATUS_LABELS, PROPOSAL_STATUS_TAG_TYPES,
} from '@/utils/constants'
import { formatTime } from '@/utils/format'

const router = useRouter()
const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const emptyText = ref('暂无投标文件')

const filterForm = reactive({
  status: '',
  bid_document_id: '',
  page: 1,
  size: 20,
})

async function fetchList() {
  loading.value = true
  emptyText.value = '加载中...'
  try {
    const params = { page: filterForm.page, size: filterForm.size }
    if (filterForm.status) params.status = filterForm.status
    if (filterForm.bid_document_id) params.bid_document_id = filterForm.bid_document_id
    const res = await listProposals(params)
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
    emptyText.value = '暂无投标文件'
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
  filterForm.status = ''
  filterForm.bid_document_id = ''
  filterForm.page = 1
  fetchList()
}

function goCreate() {
  router.push('/proposals/create')
}

function goDetail(row) {
  router.push(`/proposals/${row.id}`)
}

function goBid(id) {
  router.push(`/bids/${id}`)
}

async function handleDownload(row) {
  try {
    const res = await downloadProposal(row.id)
    const url = window.URL.createObjectURL(res)
    const a = document.createElement('a')
    a.href = url
    a.download = row.file_info?.name
      ? row.file_info.name
      : `${row.proposal_no}.docx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('文件下载已开始')
  } catch (e) {
    // 错误提示由拦截器统一处理
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
</style>
