<template>
  <!-- 知识文档列表页:分页 / 关键字 / Embedding 状态过滤 / Chunk 数 / 删除 -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="关键字">
          <el-input
            v-model="filterForm.keyword"
            placeholder="文档编号 / 标题"
            clearable
            style="width: 220px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="Embedding">
          <el-select
            v-model="filterForm.embedding_status"
            placeholder="全部"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="(label, key) in EMBEDDING_STATUS_LABELS"
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
          <span>知识库</span>
          <el-button
            v-if="canManage"
            type="primary"
            :icon="Upload"
            @click="router.push('/knowledge/upload')"
          >
            上传知识
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
        <el-table-column label="文档编号" prop="doc_no" min-width="220" show-overflow-tooltip />
        <el-table-column label="标题" prop="title" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain">
              {{ (row.file_info && row.file_info.type) || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Embedding 状态" width="140">
          <template #default="{ row }">
            <EmbeddingStatusTag
              :status="row.embedding_status"
              :error-message="row.error_message"
            />
          </template>
        </el-table-column>
        <el-table-column label="Chunk 数" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.chunk_count || 0 }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件大小" width="110">
          <template #default="{ row }">
            {{ formatFileSize(row.file_info && row.file_info.size) }}
          </template>
        </el-table-column>
        <el-table-column label="上传人" width="120">
          <template #default="{ row }">
            <span v-if="row.uploader">{{ row.uploader.username }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              link
              :icon="View"
              @click="handleViewDetail(row)"
            >
              详情
            </el-button>
            <el-button
              v-if="canManage"
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
  </div>
</template>

<script setup>
/**
 * 知识文档列表页(Sprint 4 - v0.6.0)
 *
 * 职责:
 * - 调用 listKnowledgeDocuments 真实接口获取数据
 * - 支持分页 / 关键字搜索 / Embedding 状态过滤
 * - 展示:文档编号 / 标题 / 类型 / Embedding 状态 / Chunk 数 / 文件大小 / 上传人 / 时间
 * - admin / contract_manager 可上传 / 删除;employee 仅查看(知识库为公共知识)
 * - 点击"详情"跳转 /knowledge/:id;点击"删除"软删 + 移除 FAISS 向量
 *
 * 权限:
 * - 全部角色可查看列表(employee 亦可)
 * - 上传 / 删除仅 admin / contract_manager(前端控显 + 后端 role_required 兜底)
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Upload, View, Delete } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import {
  listKnowledgeDocuments,
  deleteKnowledgeDocument,
} from '@/api/knowledge'
import EmbeddingStatusTag from '@/components/knowledge/EmbeddingStatusTag.vue'
import { EMBEDDING_STATUS_LABELS } from '@/utils/constants'
import { formatFileSize, formatTime } from '@/utils/format'

const router = useRouter()
const authStore = useAuthStore()

// 权限:admin / contract_manager 可上传 / 删除
const canManage = computed(() => authStore.isManager)

// ---------- 筛选表单 ----------
const filterForm = reactive({
  keyword: '',
  embedding_status: '',
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
  const hasFilter = filterForm.keyword || filterForm.embedding_status
  return hasFilter ? '未找到匹配的知识文档,请调整搜索条件' : '暂无知识文档,请上传知识文档以启用 RAG 问答'
})

async function loadList() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      size: pagination.size,
    }
    if (filterForm.keyword) params.keyword = filterForm.keyword
    if (filterForm.embedding_status) params.embedding_status = filterForm.embedding_status

    const res = await listKnowledgeDocuments(params)
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
  filterForm.keyword = ''
  filterForm.embedding_status = ''
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
  router.push(`/knowledge/${row.id}`)
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除知识文档「${row.title}」吗?将同时从 FAISS 索引中移除其向量,该操作不可恢复。`,
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
    await deleteKnowledgeDocument(row.id)
    ElMessage.success('删除成功')
    // 若当前页只剩一条且非首页,回退一页
    if (tableData.value.length === 1 && pagination.page > 1) {
      pagination.page -= 1
    }
    loadList()
  } catch (err) {
    // 错误已由拦截器统一提示
  }
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
</style>
