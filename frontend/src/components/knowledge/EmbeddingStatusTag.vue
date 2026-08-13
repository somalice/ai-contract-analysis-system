<template>
  <!-- 知识文档 Embedding 状态标签(Sprint 4 - v0.6.0) -->
  <el-tooltip
    v-if="needTooltip"
    :content="errorMessage"
    placement="top"
  >
    <el-tag :type="tagType" size="small" effect="light">
      <el-icon class="error-icon"><WarningFilled /></el-icon>
      {{ label }}
    </el-tag>
  </el-tooltip>
  <el-tag v-else :type="tagType" size="small" effect="light">
    <el-icon v-if="status === 'processing'" class="is-loading"><Loading /></el-icon>
    {{ label }}
  </el-tag>
</template>

<script setup>
/**
 * Embedding 状态标签
 *
 * 职责:
 * - 根据 embedding_status 渲染 el-tag
 * - processing 时显示 loading 图标
 * - failed 时附带 error_message 提示(tooltip)
 *
 * 状态:pending(待处理)/ processing(处理中)/ completed(已向量化)/ failed(处理失败)
 */
import { computed } from 'vue'
import { Loading, WarningFilled } from '@element-plus/icons-vue'
import {
  EMBEDDING_STATUS,
  EMBEDDING_STATUS_LABELS,
  EMBEDDING_STATUS_TAG_TYPES,
} from '@/utils/constants'

const props = defineProps({
  status: {
    type: String,
    default: '',
  },
  errorMessage: {
    type: String,
    default: '',
  },
})

const tagType = computed(
  () => EMBEDDING_STATUS_TAG_TYPES[props.status] || 'info'
)

const label = computed(
  () => EMBEDDING_STATUS_LABELS[props.status] || props.status || '-'
)

// 是否需要 tooltip 展示错误详情
const needTooltip = computed(
  () => props.status === EMBEDDING_STATUS.FAILED && !!props.errorMessage
)
</script>

<style scoped>
.is-loading {
  margin-right: 2px;
  animation: rotating 1.5s linear infinite;
}

.error-icon {
  margin-right: 2px;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
