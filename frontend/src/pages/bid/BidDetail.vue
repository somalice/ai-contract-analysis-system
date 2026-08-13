<template>
  <!-- 招标文件详情页:基本信息 / 需求解析(15 字段) / 全文预览 / 生成投标 -->
  <div class="page-container" v-loading="loading">
    <!-- 顶部操作栏 -->
    <el-card class="action-card mb-16" shadow="never">
      <div class="action-bar">
        <el-button :icon="Back" @click="router.back()">返回</el-button>
        <div class="action-right">
          <el-button
            v-if="bid?.parse_status === 'failed'"
            type="warning"
            :icon="Refresh"
            :loading="reparsing"
            @click="handleReparse"
          >
            重新解析
          </el-button>
          <el-button
            v-if="bid?.parse_status === 'success'"
            type="success"
            :icon="MagicStick"
            @click="goGenerate"
          >
            生成投标文件
          </el-button>
          <el-button
            v-if="isManager"
            type="danger"
            :icon="Delete"
            @click="handleDelete"
          >
            删除
          </el-button>
        </div>
      </div>
    </el-card>

    <template v-if="bid">
      <!-- 状态总览 -->
      <el-card class="mb-16 status-overview" shadow="never" :class="overviewCardClass">
        <div class="overview-content">
          <div class="overview-left">
            <div class="overview-label">解析状态</div>
            <div class="overview-level">
              <el-tag
                :type="BID_PARSE_STATUS_TAG_TYPES[bid.parse_status] || 'info'"
                effect="dark"
                size="large"
              >
                {{ BID_PARSE_STATUS_LABELS[bid.parse_status] || bid.parse_status }}
              </el-tag>
            </div>
          </div>
          <div class="overview-right">
            <div class="overview-stat">
              <span class="stat-label">字段数</span>
              <span class="stat-value">{{ bid.requirement?.field_count ?? 0 }} / 15</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">置信度</span>
              <span class="stat-value info">
                {{ bid.requirement?.confidence ? (bid.requirement.confidence * 100).toFixed(0) + '%' : '-' }}
              </span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">页数</span>
              <span class="stat-value">{{ bid.page_count }}</span>
            </div>
            <div class="overview-stat">
              <span class="stat-label">文本长度</span>
              <span class="stat-value">{{ bid.text_length }}</span>
            </div>
          </div>
        </div>
        <el-alert
          v-if="bid.parse_status === 'failed' && bid.error_message"
          type="error"
          :closable="false"
          show-icon
          class="mt-12"
        >
          <template #title>解析失败:{{ bid.error_message }}</template>
        </el-alert>
      </el-card>

      <!-- 基本信息 -->
      <el-card class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Document /></el-icon>
            <span>招标文件信息</span>
          </div>
        </template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="招标编号">{{ bid.bid_no }}</el-descriptions-item>
          <el-descriptions-item label="招标标题">{{ bid.title }}</el-descriptions-item>
          <el-descriptions-item label="文件类型">{{ bid.file_info?.type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="文件名">{{ bid.file_info?.name }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ formatFileSize(bid.file_info?.size) }}</el-descriptions-item>
          <el-descriptions-item label="提取方法">{{ bid.extract_method }}</el-descriptions-item>
          <el-descriptions-item label="上传者">
            {{ bid.uploader?.username || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(bid.created_time) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatTime(bid.updated_time) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 需求解析(15 字段) -->
      <el-card v-if="requirement" class="mb-16" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Collection /></el-icon>
            <span>需求解析(15 字段)</span>
            <el-tag size="small" type="info" class="header-tag">
              {{ requirement.field_count }} / 15 字段 · 置信度
              {{ requirement.confidence ? (requirement.confidence * 100).toFixed(0) + '%' : '-' }}
            </el-tag>
          </div>
        </template>

        <!-- 文本类型字段 -->
        <el-descriptions :column="2" border>
          <el-descriptions-item
            v-for="field in textFieldList"
            :key="field.key"
            :label="field.label"
          >
            <span v-if="field.value">{{ field.value }}</span>
            <span v-else class="text-muted">(未提取)</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 列表类型字段 -->
        <div class="list-fields">
          <el-card
            v-for="field in listFieldList"
            :key="field.key"
            shadow="never"
            class="list-field-card"
          >
            <template #header>
              <div class="list-field-header">
                <span>{{ field.label }}</span>
                <el-tag size="small" type="info">{{ field.value?.length || 0 }} 项</el-tag>
              </div>
            </template>
            <ul v-if="field.value && field.value.length" class="list-field-ul">
              <li v-for="(item, idx) in field.value" :key="idx">{{ item }}</li>
            </ul>
            <div v-else class="text-muted">(未提取)</div>
          </el-card>
        </div>
      </el-card>

      <!-- 全文预览 -->
      <el-card v-if="bid.text_content" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Document /></el-icon>
            <span>招标文件全文</span>
            <el-button
              size="small"
              :icon="showFullText ? ArrowUp : ArrowDown"
              class="header-tag"
              @click="showFullText = !showFullText"
            >
              {{ showFullText ? '收起' : '展开' }}
            </el-button>
          </div>
        </template>
        <pre v-if="showFullText" class="full-text">{{ bid.text_content }}</pre>
        <pre v-else class="full-text-preview">{{ textPreview }}</pre>
      </el-card>
    </template>

    <el-empty v-else-if="!loading" description="招标文件不存在或加载失败" />
  </div>
</template>

<script setup>
/**
 * 招标文件详情页(Sprint 7 - v0.9.0)
 *
 * 展示内容:
 * 1. 解析状态总览(parse_status / 字段数 / 置信度 / 页数 / 文本长度)
 * 2. 招标文件基本信息(编号 / 标题 / 文件信息 / 提取方法 / 上传者 / 时间)
 * 3. 需求解析 15 字段(text 字段表格 + list 字段卡片)
 * 4. 招标文件全文预览(可展开/收起)
 * 5. 重新解析 / 生成投标 / 删除操作
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Back, Document, Collection, MagicStick, Refresh, Delete,
  ArrowUp, ArrowDown,
} from '@element-plus/icons-vue'
import { getBidDocumentDetail, parseBidDocument, deleteBidDocument } from '@/api/bid'
import { useAuthStore } from '@/store/auth'
import {
  BID_PARSE_STATUS_LABELS, BID_PARSE_STATUS_TAG_TYPES,
  BID_REQUIREMENT_FIELDS,
} from '@/utils/constants'
import { formatTime, formatFileSize } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isManager = computed(() => authStore.isManager)

const loading = ref(false)
const reparsing = ref(false)
const bid = ref(null)
const showFullText = ref(false)

const requirement = computed(() => bid.value?.requirement || null)

const overviewCardClass = computed(() => {
  const s = bid.value?.parse_status
  if (s === 'success') return 'overview-success'
  if (s === 'failed') return 'overview-failed'
  if (s === 'processing') return 'overview-processing'
  return ''
})

// 文本类型字段(单值)
const textFieldList = computed(() => {
  const data = requirement.value?.requirement_data || {}
  return BID_REQUIREMENT_FIELDS
    .filter((f) => f.type === 'text')
    .map((f) => ({ ...f, value: data[f.key] }))
})

// 列表类型字段(数组)
const listFieldList = computed(() => {
  const data = requirement.value?.requirement_data || {}
  return BID_REQUIREMENT_FIELDS
    .filter((f) => f.type === 'list')
    .map((f) => ({ ...f, value: data[f.key] }))
})

// 全文预览(前 500 字符)
const textPreview = computed(() => {
  const t = bid.value?.text_content || ''
  return t.length > 500 ? t.slice(0, 500) + '...' : t
})

async function fetchDetail() {
  loading.value = true
  try {
    const res = await getBidDocumentDetail(route.params.id, true)
    bid.value = res.data
  } catch (e) {
    // 错误提示由拦截器统一处理
  } finally {
    loading.value = false
  }
}

async function handleReparse() {
  if (!bid.value) return
  try {
    await ElMessageBox.confirm(
      `确定要重新解析招标文件"${bid.value.title}"吗?将重新执行 Pipeline 并覆盖原需求。`,
      '提示',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    reparsing.value = true
    const res = await parseBidDocument(bid.value.id)
    bid.value = res.data
    if (res.data.parse_status === 'success') {
      ElMessage.success('招标文件解析完成')
    } else {
      ElMessage.warning('招标文件解析失败,请稍后重试')
    }
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      // 错误提示由拦截器统一处理
    }
  } finally {
    reparsing.value = false
  }
}

async function handleDelete() {
  if (!bid.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除招标文件"${bid.value.title}"吗?关联的需求与生成记录将一并删除,该操作不可恢复。`,
      '危险操作',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'error' }
    )
    await deleteBidDocument(bid.value.id)
    ElMessage.success('招标文件已删除')
    router.push('/bids')
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      // 错误提示由拦截器统一处理
    }
  }
}

function goGenerate() {
  if (bid.value) {
    router.push(`/proposals/create?bid_document_id=${bid.value.id}`)
  }
}

import { onMounted } from 'vue'
onMounted(() => {
  fetchDetail()
})
</script>

<style scoped>
.page-container { padding: 0; }
.mb-16 { margin-bottom: 16px; }
.mt-12 { margin-top: 12px; }
.action-card { border: 1px solid #ebeef5; }
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.action-right {
  display: flex;
  gap: 8px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-tag {
  margin-left: auto;
}

/* 状态总览卡片 */
.status-overview {
  border-left: 4px solid #409eff;
}
.overview-success {
  border-left-color: #67c23a;
  background: linear-gradient(90deg, rgba(103,194,58,0.05) 0%, transparent 100%);
}
.overview-failed {
  border-left-color: #f56c6c;
  background: linear-gradient(90deg, rgba(245,108,108,0.05) 0%, transparent 100%);
}
.overview-processing {
  border-left-color: #e6a23c;
  background: linear-gradient(90deg, rgba(230,162,60,0.05) 0%, transparent 100%);
}
.overview-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.overview-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.overview-label {
  font-size: 13px;
  color: #909399;
}
.overview-right {
  display: flex;
  gap: 32px;
}
.overview-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.stat-value {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}
.stat-value.info { color: #409eff; }

/* 列表字段卡片 */
.list-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.list-field-card {
  background: #fafafa;
}
.list-field-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.list-field-ul {
  margin: 0;
  padding-left: 20px;
  color: #303133;
  font-size: 13px;
  line-height: 1.8;
}

/* 全文 */
.full-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
  max-height: 600px;
  overflow-y: auto;
  background: #f5f7fa;
  padding: 12px 16px;
  border-radius: 4px;
  margin: 0;
}
.full-text-preview {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
  max-height: 160px;
  overflow: hidden;
  position: relative;
  background: #f5f7fa;
  padding: 12px 16px;
  border-radius: 4px;
  margin: 0;
}

.text-muted { color: #909399; font-size: 12px; font-style: italic; }
</style>
