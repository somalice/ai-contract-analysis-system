<template>
  <!-- 知识文档详情页:基本信息 / 文件信息 / Embedding 状态 / Chunk 预览 -->
  <div class="page-container">
    <!-- 顶部操作栏 -->
    <el-card shadow="never" class="mb-16">
      <div class="top-bar">
        <el-button :icon="Back" @click="router.back()">返回</el-button>
        <div class="top-title">
          <span class="title-text">{{ document.title || '知识文档详情' }}</span>
          <EmbeddingStatusTag
            v-if="document.embedding_status"
            :status="document.embedding_status"
            :error-message="document.error_message"
          />
        </div>
        <el-button
          v-if="canManage"
          type="danger"
          :icon="Delete"
          @click="handleDelete"
        >
          删除
        </el-button>
      </div>
    </el-card>

    <div v-loading="loading">
      <!-- 基本信息 -->
      <el-card shadow="never" class="mb-16">
        <template #header>基本信息</template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="文档编号">{{ document.doc_no }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ document.title }}</el-descriptions-item>
          <el-descriptions-item label="来源类型">
            {{ sourceTypeLabel }}
          </el-descriptions-item>
          <el-descriptions-item label="文档状态">
            <el-tag size="small" :type="document.status === 'active' ? 'success' : 'info'">
              {{ document.status === 'active' ? '可用' : '已删除' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="页数">{{ document.page_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="文本长度">{{ document.text_length || 0 }} 字符</el-descriptions-item>
          <el-descriptions-item label="Chunk 数量">
            <el-tag size="small" effect="plain">{{ document.chunk_count || 0 }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="已入向量库">
            <el-tag size="small" :type="document.vector_indexed ? 'success' : 'info'">
              {{ document.vector_indexed ? '是' : '否' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 文件信息 -->
      <el-card shadow="never" class="mb-16">
        <template #header>文件信息</template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="原始文件名">
            {{ document.file_info && document.file_info.name }}
          </el-descriptions-item>
          <el-descriptions-item label="文件大小">
            {{ formatFileSize(document.file_info && document.file_info.size) }}
          </el-descriptions-item>
          <el-descriptions-item label="文件类型">
            <el-tag size="small" type="info" effect="plain">
              {{ document.file_info && document.file_info.type }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 上传人 / 时间 -->
      <el-card shadow="never" class="mb-16">
        <template #header>上传信息</template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="上传人">
            <span v-if="document.uploader">{{ document.uploader.username }}</span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="上传人角色">
            <span v-if="document.uploader">
              {{ roleLabel(document.uploader.role) }}
            </span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatTime(document.created_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatTime(document.updated_time) }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 错误信息 -->
      <el-card v-if="document.error_message" shadow="never" class="mb-16">
        <template #header>处理失败原因</template>
        <el-alert type="error" :closable="false" show-icon>
          <template #title>{{ document.error_message }}</template>
        </el-alert>
      </el-card>

      <!-- Chunk 预览(前 3 个) -->
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>Chunk 预览(前 {{ chunksPreview.length }} 个)</span>
            <span class="chunk-tip">完整 Chunk 数据存于 knowledge_chunks 表,可经 RAG 检索</span>
          </div>
        </template>

        <el-empty
          v-if="!chunksPreview.length"
          description="无 Chunk 数据(可能解析失败或文本为空)"
          :image-size="80"
        />
        <div v-else class="chunks-list">
          <div v-for="chunk in chunksPreview" :key="chunk.id" class="chunk-item">
            <div class="chunk-header">
              <el-tag size="small" type="primary">Chunk #{{ chunk.chunk_index }}</el-tag>
              <el-tag v-if="chunk.page_number > 0" size="small" type="info" effect="plain">
                P.{{ chunk.page_number }}
              </el-tag>
              <span class="chunk-offset">
                offset: {{ chunk.start_offset }} - {{ chunk.end_offset }}
              </span>
              <span class="chunk-tokens">~{{ chunk.token_count }} tokens</span>
              <el-tag
                v-if="chunk.vector_id !== null && chunk.vector_id !== undefined"
                size="small"
                type="success"
                effect="plain"
              >
                已向量化 vec={{ chunk.vector_id }}
              </el-tag>
            </div>
            <div class="chunk-text">{{ chunk.text }}</div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
/**
 * 知识文档详情页(Sprint 4 - v0.6.0)
 *
 * 职责:
 * - 调用 getKnowledgeDocumentDetail 获取详情(含前 3 个 chunk 预览)
 * - 展示:基本信息 / 文件信息 / 上传信息 / 处理失败原因 / Chunk 预览
 * - admin / contract_manager 可删除
 *
 * Chunk 预览展示:chunk_index / page_number / start_offset / end_offset /
 *   token_count / vector_id / text(截断 200 字)
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Delete } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import {
  getKnowledgeDocumentDetail,
  deleteKnowledgeDocument,
} from '@/api/knowledge'
import EmbeddingStatusTag from '@/components/knowledge/EmbeddingStatusTag.vue'
import { ROLE_LABELS } from '@/utils/constants'
import { formatFileSize, formatTime } from '@/utils/format'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const canManage = computed(() => authStore.isManager)
const loading = ref(false)

const document = reactive({})
const chunksPreview = computed(() => document.chunks_preview || [])

const sourceTypeLabel = computed(() => {
  const map = { manual_upload: '手动上传', contract: '合同导入' }
  return map[document.source_type] || document.source_type || '-'
})

function roleLabel(role) {
  return ROLE_LABELS[role] || role || '-'
}

async function loadDetail() {
  loading.value = true
  try {
    const id = route.params.id
    const res = await getKnowledgeDocumentDetail(id)
    Object.assign(document, res.data.document)
  } catch (err) {
    // 错误已由拦截器统一提示
  } finally {
    loading.value = false
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(
      `确定删除知识文档「${document.title}」吗?将同时从 FAISS 索引中移除其向量。`,
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
    await deleteKnowledgeDocument(document.id)
    ElMessage.success('删除成功')
    router.push('/knowledge')
  } catch (err) {
    // 错误已由拦截器统一提示
  }
}

onMounted(() => {
  loadDetail()
})
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.top-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  justify-content: center;
}

.title-text {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chunk-tip {
  font-size: 12px;
  color: #909399;
}

.chunks-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chunk-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px 16px;
  background: #fafafa;
}

.chunk-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.chunk-offset,
.chunk-tokens {
  font-size: 12px;
  color: #909399;
  font-variant-numeric: tabular-nums;
}

.chunk-text {
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
  white-space: pre-wrap;
  background: #fff;
  padding: 10px 12px;
  border-radius: 4px;
  border-left: 2px solid #dcdfe6;
}
</style>
