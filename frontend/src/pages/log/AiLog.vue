<template>
  <!-- AI 调用日志列表页(Sprint 8 - v1.0.0) -->
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card class="filter-card mb-16" shadow="never">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item label="Agent 类型">
          <el-select
            v-model="filterForm.agent_type"
            placeholder="全部"
            clearable
            style="width: 180px"
          >
            <el-option
              v-for="(label, key) in AI_AGENT_TYPE_LABELS"
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
            style="width: 120px"
          >
            <el-option
              v-for="(label, key) in LOG_STATUS_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="用户 ID">
          <el-input
            v-model="filterForm.user_id"
            placeholder="输入用户 ID"
            clearable
            style="width: 140px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filterForm.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:MM:SS"
            style="width: 380px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
          <el-button :icon="RefreshRight" @click="loadList">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>AI 调用日志</span>
          <el-tag size="small" type="info">仅 admin 可查看</el-tag>
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
        <el-table-column label="ID" prop="id" width="70" align="center" />
        <el-table-column label="Agent 类型" min-width="150">
          <template #default="{ row }">
            <el-tag size="small" effect="dark" type="primary">
              {{ AI_AGENT_TYPE_LABELS[row.agent_type] || row.agent_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="用户" min-width="120">
          <template #default="{ row }">
            <div v-if="row.username">
              <span>{{ row.username }}</span>
              <span class="meta-secondary">(#{{ row.user_id }})</span>
            </div>
            <span v-else class="meta-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="模型" min-width="130">
          <template #default="{ row }">
            <span v-if="row.model">{{ row.model }}</span>
            <span v-else class="meta-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="Prompt 版本" min-width="130">
          <template #default="{ row }">
            <el-tag v-if="row.prompt_version" size="small" effect="plain">
              {{ row.prompt_version }}
            </el-tag>
            <span v-else class="meta-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="Token 用量" min-width="140" align="center">
          <template #default="{ row }">
            <div v-if="row.total_tokens != null" class="token-info">
              <span class="token-total">{{ row.total_tokens }}</span>
              <span class="token-breakdown meta-secondary">
                (↑{{ row.input_tokens || 0 }} / ↓{{ row.output_tokens || 0 }})
              </span>
            </div>
            <span v-else class="meta-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.latency_ms != null">{{ formatLatency(row.latency_ms) }}</span>
            <span v-else class="meta-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              :type="LOG_STATUS_TAG_TYPES[row.status] || 'info'"
              effect="dark"
              size="small"
            >
              {{ LOG_STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="调用时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_time) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              link
              :icon="View"
              @click="openDetail(row)"
            >
              详情
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
          :page-sizes="[20, 50, 100, 200]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      title="AI 调用日志详情"
      width="75%"
      destroy-on-close
    >
      <el-descriptions v-if="detailData" :column="2" border>
        <el-descriptions-item label="日志 ID">{{ detailData.id }}</el-descriptions-item>
        <el-descriptions-item label="调用时间">{{ formatTime(detailData.created_time) }}</el-descriptions-item>
        <el-descriptions-item label="Agent 类型">
          <el-tag size="small" effect="dark" type="primary">
            {{ AI_AGENT_TYPE_LABELS[detailData.agent_type] || detailData.agent_type }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag
            :type="LOG_STATUS_TAG_TYPES[detailData.status] || 'info'"
            effect="dark"
            size="small"
          >
            {{ LOG_STATUS_LABELS[detailData.status] || detailData.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="用户">
          <span v-if="detailData.username">{{ detailData.username }} (#{{ detailData.user_id }})</span>
          <span v-else class="meta-secondary">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="模型">
          {{ detailData.model || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="Prompt 版本">
          <el-tag v-if="detailData.prompt_version" size="small" effect="plain">
            {{ detailData.prompt_version }}
          </el-tag>
          <span v-else class="meta-secondary">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="耗时">
          {{ detailData.latency_ms != null ? formatLatency(detailData.latency_ms) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="关联对象">
          <span v-if="detailData.related_type">
            {{ detailData.related_type }} #{{ detailData.related_id }}
          </span>
          <span v-else class="meta-secondary">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="Token 总量">
          <span v-if="detailData.total_tokens != null" class="token-total">
            {{ detailData.total_tokens }}
          </span>
          <span v-else class="meta-secondary">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="输入 Token (Prompt)">
          {{ detailData.input_tokens != null ? detailData.input_tokens : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="输出 Token (Completion)">
          {{ detailData.output_tokens != null ? detailData.output_tokens : '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="detailData.error_message" label="错误信息" :span="2">
          <pre class="json-block error-block">{{ detailData.error_message }}</pre>
        </el-descriptions-item>
        <el-descriptions-item v-if="detailData.trace_summary" label="Trace 摘要(工具 / LLM 统计)" :span="2">
          <pre class="json-block">{{ formatJson(detailData.trace_summary) }}</pre>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * AI 调用日志列表页(Sprint 8 - v1.0.0)
 *
 * 职责:
 * - 调用 listAiLogs 获取 AI 调用日志
 * - 支持分页 / Agent类型筛选 / 状态筛选 / 用户筛选 / 时间范围查询
 * - 重点展示:agent_type / model / prompt_version / token(input/output/total) / latency / status / error
 * - 详情弹窗含 trace_summary(工具调用统计 + LLM 统计,JSON 格式化展示)
 *
 * 权限:
 * - 仅 admin 可访问(路由 meta.roles + 后端 role_required 兜底)
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { Search, Refresh, RefreshRight, View } from '@element-plus/icons-vue'
import { listAiLogs, getAiLog } from '@/api/log'
import {
  LOG_STATUS_LABELS,
  LOG_STATUS_TAG_TYPES,
  AI_AGENT_TYPE_LABELS,
} from '@/utils/constants'
import { formatTime } from '@/utils/format'

// ---------- 筛选表单 ----------
const filterForm = reactive({
  agent_type: '',
  status: '',
  user_id: '',
  timeRange: null,
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
  const hasFilter =
    filterForm.agent_type ||
    filterForm.status ||
    filterForm.user_id ||
    filterForm.timeRange
  return hasFilter ? '未找到匹配的 AI 调用日志,请调整搜索条件' : '暂无 AI 调用日志'
})

// ---------- 详情弹窗 ----------
const detailVisible = ref(false)
const detailData = ref(null)

// ---------- 工具函数 ----------
function formatJson(obj) {
  if (!obj) return ''
  if (typeof obj === 'string') {
    try {
      return JSON.stringify(JSON.parse(obj), null, 2)
    } catch {
      return obj
    }
  }
  return JSON.stringify(obj, null, 2)
}

function formatLatency(ms) {
  if (ms == null) return '-'
  if (ms < 1000) return ms + 'ms'
  return (ms / 1000).toFixed(2) + 's'
}

function buildParams() {
  const params = {
    page: pagination.page,
    size: pagination.size,
  }
  if (filterForm.agent_type) params.agent_type = filterForm.agent_type
  if (filterForm.status) params.status = filterForm.status
  if (filterForm.user_id) params.user_id = filterForm.user_id
  if (filterForm.timeRange && filterForm.timeRange.length === 2) {
    params.start_time = filterForm.timeRange[0]
    params.end_time = filterForm.timeRange[1]
  }
  return params
}

// ---------- 数据加载 ----------
async function loadList() {
  loading.value = true
  try {
    const res = await listAiLogs(buildParams())
    tableData.value = res.data.items || []
    pagination.total = res.data.total || 0
  } catch {
    tableData.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

// ---------- 筛选操作 ----------
function handleSearch() {
  pagination.page = 1
  loadList()
}

function handleReset() {
  filterForm.agent_type = ''
  filterForm.status = ''
  filterForm.user_id = ''
  filterForm.timeRange = null
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

// ---------- 详情 ----------
async function openDetail(row) {
  detailData.value = null
  detailVisible.value = true
  try {
    const res = await getAiLog(row.id)
    detailData.value = res.data
  } catch {
    // 列表数据兜底:接口失败时用列表行数据展示
    detailData.value = row
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

.meta-secondary {
  color: #909399;
  font-size: 12px;
}

.token-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.4;
}

.token-total {
  font-weight: 600;
  color: #409eff;
}

.token-breakdown {
  font-size: 11px;
}

.json-block {
  margin: 0;
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
}

.error-block {
  background-color: #fef0f0;
  color: #f56c6c;
}
</style>
