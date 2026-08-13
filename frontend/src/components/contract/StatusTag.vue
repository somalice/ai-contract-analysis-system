<template>
  <!-- 合同状态标签组件 -->
  <div class="status-tag-wrapper">
    <el-tag :type="statusType" size="small" effect="light">
      {{ statusLabel }}
    </el-tag>
    <el-tag
      v-if="showAnalysis && analysisStatus"
      :type="analysisType"
      size="small"
      effect="plain"
      class="analysis-tag"
    >
      <el-icon v-if="analysisStatus === 'processing'" class="is-loading">
        <Loading />
      </el-icon>
      {{ analysisLabel }}
    </el-tag>
  </div>
</template>

<script setup>
/**
 * 合同状态标签
 *
 * 显示:
 * - 主状态标签(draft/reviewed/archived)
 * - 可选:AI 分析状态标签(processing/completed/failed)
 *
 * 与后端 Contract.VALID_STATUSES / VALID_ANALYSIS_STATUSES 保持一致
 */
import { computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import {
  STATUS_LABELS,
  STATUS_TAG_TYPES,
  ANALYSIS_STATUS_LABELS,
  ANALYSIS_STATUS_TAG_TYPES,
} from '@/utils/constants'

const props = defineProps({
  // 合同主状态:draft / reviewed / archived
  status: {
    type: String,
    required: true,
  },
  // 是否显示 AI 分析状态
  showAnalysis: {
    type: Boolean,
    default: false,
  },
  // AI 分析状态:processing / completed / failed / pending
  analysisStatus: {
    type: String,
    default: '',
  },
})

const statusLabel = computed(() => STATUS_LABELS[props.status] || props.status)
const statusType = computed(() => STATUS_TAG_TYPES[props.status] || 'info')

const analysisLabel = computed(
  () => ANALYSIS_STATUS_LABELS[props.analysisStatus] || props.analysisStatus
)
const analysisType = computed(
  () => ANALYSIS_STATUS_TAG_TYPES[props.analysisStatus] || 'info'
)
</script>

<style scoped>
.status-tag-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.analysis-tag {
  font-size: 12px;
}

.analysis-tag .is-loading {
  margin-right: 2px;
}
</style>
