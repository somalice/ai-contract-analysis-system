<template>
  <!-- 生成记录列表页:分页 / 状态过滤 / 模板过滤 -->
  <div class="page-container">
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="状态">
          <el-select v-model="filterForm.status" placeholder="全部" clearable style="width: 140px">
            <el-option
              v-for="(label, key) in GENERATION_STATUS_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="模板ID">
          <el-input
            v-model="filterForm.template_id"
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
          <span>合同生成记录</span>
          <el-button type="primary" :icon="MagicStick" @click="goCreate">生成新合同</el-button>
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
        <el-table-column label="生成编号" prop="generation_no" min-width="220" show-overflow-tooltip />
        <el-table-column label="使用模板" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.template">{{ row.template.name }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建的合同" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link v-if="row.contract" type="primary" @click="goContract(row.contract.id)">
              {{ row.contract.title }}
            </el-link>
            <span v-else class="text-muted">(预览,未建合同)</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="GENERATION_STATUS_TAG_TYPES[row.status] || 'info'" size="small">
              {{ GENERATION_STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="迭代" width="80" align="center">
          <template #default="{ row }">{{ row.iterations ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" link :icon="View" @click="goDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="row.status === 'success' && row.contract_id"
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
 * 生成记录列表页(Sprint 6 - v0.8.0)
 *
 * 职责:
 * - 生成记录分页(状态 / 模板过滤)
 * - admin/contract_manager 可见全部;employee 仅可见自己触发的
 * - 下载已生成的 Word
 */
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Refresh, MagicStick, View, Download } from '@element-plus/icons-vue'
import { listGenerations, downloadGeneratedContract } from '@/api/generation'
import { GENERATION_STATUS_LABELS, GENERATION_STATUS_TAG_TYPES } from '@/utils/constants'

const router = useRouter()
const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const emptyText = ref('暂无生成记录')

const filterForm = reactive({
  status: '',
  template_id: '',
  page: 1,
  size: 20,
})

async function fetchList() {
  loading.value = true
  emptyText.value = '加载中...'
  try {
    const params = { page: filterForm.page, size: filterForm.size }
    if (filterForm.status) params.status = filterForm.status
    if (filterForm.template_id) params.template_id = filterForm.template_id
    const res = await listGenerations(params)
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
    emptyText.value = '暂无生成记录'
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
  filterForm.template_id = ''
  filterForm.page = 1
  fetchList()
}

function goCreate() {
  router.push('/generation/create')
}

function goDetail(row) {
  router.push(`/generation/${row.id}`)
}

function goContract(id) {
  router.push(`/contracts/${id}`)
}

async function handleDownload(row) {
  try {
    const res = await downloadGeneratedContract(row.id)
    const url = window.URL.createObjectURL(res)
    const a = document.createElement('a')
    a.href = url
    a.download = row.contract?.title
      ? `${row.contract.title}.docx`
      : `${row.generation_no}.docx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('文件下载已开始')
  } catch (e) {
    // 错误提示由拦截器统一处理
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
.text-muted { color: #909399; font-size: 12px; }
</style>
