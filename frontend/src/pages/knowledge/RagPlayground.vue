<template>
  <!-- RAG Playground:用户问题 → 命中 Chunk + 相似度 → LLM 回答 -->
  <div class="page-container rag-playground">
    <el-row :gutter="16">
      <!-- 左侧:提问区 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="query-card">
          <template #header>
            <div class="card-header">
              <span>提问</span>
              <el-tag size="small" type="info" effect="plain">
                向量库:{{ vectorStoreStatus }}
              </el-tag>
            </div>
          </template>

          <el-form @submit.prevent="handleQuery">
            <el-form-item>
              <el-input
                v-model="query"
                type="textarea"
                :rows="5"
                placeholder="例如:付款违约条款如何约定?合同生效条件有哪些?"
                maxlength="1000"
                show-word-limit
                :disabled="loading"
                @keydown.ctrl.enter="handleQuery"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :icon="Promotion"
                :loading="loading"
                :disabled="!query.trim()"
                @click="handleQuery"
              >
                {{ loading ? '检索 + 生成中...' : '发起检索' }}
              </el-button>
              <el-button :icon="RefreshLeft" :disabled="loading" @click="handleClear">
                清空
              </el-button>
            </el-form-item>
          </el-form>

          <!-- 提示 -->
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="tip-alert"
          >
            <template #title>
              快捷键 Ctrl + Enter 发起检索。检索流程:query → Embedding → FAISS TopK →
              阈值过滤 → DeepSeek 生成回答(仅依据检索内容,未命中明确说明)。
            </template>
          </el-alert>

          <!-- 示例问题 -->
          <div class="examples">
            <div class="examples-title">示例问题</div>
            <div class="examples-list">
              <el-tag
                v-for="(ex, i) in exampleQuestions"
                :key="i"
                class="example-tag"
                effect="plain"
                @click="useExample(ex)"
              >
                {{ ex }}
              </el-tag>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧:回答区 -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="answer-card">
          <template #header>
            <div class="card-header">
              <span>LLM 回答</span>
              <div v-if="result" class="hit-info">
                <el-tag size="small" :type="result.hit_count > 0 ? 'success' : 'info'">
                  命中 {{ result.hit_count }} 条
                </el-tag>
                <el-tag
                  v-if="result.llm_error"
                  size="small"
                  type="danger"
                  effect="plain"
                >
                  LLM 异常
                </el-tag>
              </div>
            </div>
          </template>

          <!-- 空状态 -->
          <el-empty
            v-if="!result && !loading"
            description="发起检索后,这里将展示 LLM 回答与命中来源"
            :image-size="80"
          />

          <!-- 加载中 -->
          <div v-if="loading" class="loading-block">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>正在检索知识库并生成回答,请稍候...</span>
          </div>

          <!-- 结果 -->
          <div v-if="result && !loading" class="answer-block">
            <div class="answer-text">{{ result.answer }}</div>
            <el-alert
              v-if="result.llm_error"
              type="warning"
              :closable="false"
              show-icon
              class="llm-error-alert"
            >
              <template #title>
                LLM 生成失败:{{ result.llm_error }}(以下仍为命中 Chunk,供参考)
              </template>
            </el-alert>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 命中 Chunk 列表(整行) -->
    <el-card v-if="result && result.references && result.references.length" shadow="never" class="refs-card">
      <template #header>
        <div class="card-header">
          <span>命中 Chunk({{ result.references.length }})</span>
          <span class="refs-tip">按相似度降序排列</span>
        </div>
      </template>

      <div class="refs-list">
        <div
          v-for="(ref, idx) in result.references"
          :key="ref.chunk_id"
          class="ref-item"
        >
          <div class="ref-header">
            <div class="ref-meta">
              <el-tag size="small" type="primary">{{ ref.document_label || `[文档${idx + 1}]` }}</el-tag>
              <span class="ref-title">{{ ref.document_title }}</span>
              <el-tag size="small" type="info" effect="plain">
                Chunk #{{ ref.chunk_index }}
              </el-tag>
              <el-tag v-if="ref.page_number > 0" size="small" type="info" effect="plain">
                P.{{ ref.page_number }}
              </el-tag>
            </div>
            <div class="ref-score">
              <span class="score-label">相似度</span>
              <el-progress
                :percentage="scorePercent(ref.score)"
                :color="scoreColor(ref.score)"
                :stroke-width="8"
                class="score-bar"
              />
              <span class="score-value">{{ ref.score.toFixed(4) }}</span>
            </div>
          </div>
          <div class="ref-text">{{ ref.text }}</div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * RAG Playground(Sprint 4 - v0.6.0)
 *
 * 职责:
 * - 输入用户问题 → 调用 POST /api/v1/rag/query
 * - 展示三部分:
 *   1. LLM 回答(answer)
 *   2. 命中 Chunk 列表(references:文档标注 / chunk_index / 页码 / 文本)
 *   3. 相似度分数(score 进度条 + 数值)
 * - 空知识库 / 无命中 → answer 标注"未找到相关内容"
 * - LLM 失败 → 仍展示命中 Chunk,answer 标注失败原因
 *
 * 流程(后端同步):
 *   query → retriever(TopK + 阈值)→ 关联 chunk 文本 → DeepSeek 生成回答
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion, RefreshLeft, Loading } from '@element-plus/icons-vue'
import { queryRag } from '@/api/knowledge'

const query = ref('')
const loading = ref(false)
const result = ref(null)

// 示例问题
const exampleQuestions = [
  '付款违约条款如何约定?',
  '合同生效条件有哪些?',
  '不可抗力条款的处理方式?',
  '合同解除的情形有哪些?',
]

// 向量库状态(根据最近一次检索结果推断)
const vectorStoreStatus = computed(() => {
  if (!result.value) return '未知'
  if (result.value.hit_count > 0) return '可用'
  return '空 / 无命中'
})

function useExample(ex) {
  query.value = ex
}

async function handleQuery() {
  if (!query.value.trim()) {
    ElMessage.warning('请输入查询问题')
    return
  }
  loading.value = true
  result.value = null
  try {
    const res = await queryRag(query.value.trim())
    result.value = res.data
  } catch (err) {
    // 错误已由拦截器统一提示
    result.value = null
  } finally {
    loading.value = false
  }
}

function handleClear() {
  query.value = ''
  result.value = null
}

// 相似度转百分比(归一化余弦,score ∈ [0, 1])
function scorePercent(score) {
  if (!score || score <= 0) return 0
  return Math.round(Math.min(1, score) * 100)
}

// 相似度颜色梯度
function scoreColor(score) {
  if (score >= 0.75) return '#67c23a'
  if (score >= 0.5) return '#409eff'
  if (score >= 0.35) return '#e6a23c'
  return '#909399'
}
</script>

<style scoped>
.rag-playground {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hit-info {
  display: flex;
  gap: 8px;
}

.tip-alert {
  margin-top: 8px;
}

.examples {
  margin-top: 16px;
}

.examples-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.examples-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.example-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.example-tag:hover {
  color: #409eff;
  border-color: #409eff;
}

.loading-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: #909399;
  gap: 12px;
}

.loading-block .is-loading {
  font-size: 28px;
  color: #409eff;
}

.answer-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.answer-text {
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
  white-space: pre-wrap;
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

.llm-error-alert {
  margin-top: 4px;
}

.refs-card {
  margin-top: 0;
}

.refs-tip {
  font-size: 12px;
  color: #909399;
}

.refs-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ref-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px 16px;
  background: #fafafa;
}

.ref-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.ref-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ref-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.ref-score {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 220px;
}

.score-label {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.score-bar {
  width: 120px;
}

.score-value {
  font-size: 12px;
  color: #606266;
  font-variant-numeric: tabular-nums;
  min-width: 50px;
}

.ref-text {
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
  white-space: pre-wrap;
  background: #fff;
  padding: 10px 12px;
  border-radius: 4px;
  border-left: 2px solid #dcdfe6;
}

@media (max-width: 768px) {
  .ref-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .ref-score {
    width: 100%;
  }
}
</style>
