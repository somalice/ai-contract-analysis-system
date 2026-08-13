<template>
  <!-- 模板详情页:模板信息 + 变量清单 + 启停/删除操作 -->
  <div class="page-container">
    <el-card v-loading="loading" shadow="never">
      <template #header>
        <div class="card-header">
          <span>模板详情</span>
          <div>
            <el-button type="primary" :icon="MagicStick" @click="goGenerate">
              使用此模板生成合同
            </el-button>
            <el-button :icon="Back" @click="goBack">返回列表</el-button>
          </div>
        </div>
      </template>

      <template v-if="template">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="模板编号">{{ template.template_no }}</el-descriptions-item>
          <el-descriptions-item label="模板名称">{{ template.name }}</el-descriptions-item>
          <el-descriptions-item label="合同类型">{{ template.contract_type }}</el-descriptions-item>
          <el-descriptions-item label="模板版本">
            <el-tag size="small" type="success">{{ template.version || 'v1.0' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="TEMPLATE_STATUS_TAG_TYPES[template.status] || 'info'" size="small">
              {{ TEMPLATE_STATUS_LABELS[template.status] || template.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="变量数量">{{ template.variable_count }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">
            {{ formatFileSize(template.file_info?.size) }}
          </el-descriptions-item>
          <el-descriptions-item label="创建者">
            {{ template.creator?.username || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatTime(template.created_time) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间" :span="2">
            {{ formatTime(template.updated_time) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="template.description" label="模板说明" :span="2">
            {{ template.description }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 变量清单 -->
        <el-card shadow="never" class="section-card">
          <template #header>
            <span>变量清单(模板中 <code>&#123;&#123;variable&#125;&#125;</code> 占位符)</span>
          </template>
          <el-table
            v-if="template.variables?.length"
            :data="template.variables"
            stripe
            border
            style="width: 100%"
          >
            <el-table-column label="#" type="index" width="60" align="center" />
            <el-table-column label="变量名" prop="name" min-width="180" />
            <el-table-column label="显示名" prop="label" min-width="180" />
            <el-table-column label="必填" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.required ? 'danger' : 'info'" size="small">
                  {{ row.required ? '必填' : '可选' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="示例值" prop="sample" min-width="200" show-overflow-tooltip />
          </el-table>
          <el-empty v-else description="该模板未解析到变量" />
        </el-card>

        <!-- 管理员操作区 -->
        <el-card v-if="isManager" shadow="never" class="section-card">
          <template #header>
            <span>管理操作(仅管理员)</span>
          </template>
          <div class="actions">
            <el-button
              :icon="template.status === 'active' ? CircleClose : CircleCheck"
              @click="handleToggleStatus"
            >
              {{ template.status === 'active' ? '停用模板' : '启用模板' }}
            </el-button>
            <el-button type="danger" :icon="Delete" @click="handleDelete">
              删除模板
            </el-button>
          </div>
        </el-card>
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 模板详情页(Sprint 6 - v0.8.0)
 *
 * 职责:
 * - 展示模板信息 + 变量清单
 * - admin/contract_manager 可启停 / 删除模板
 * - 跳转到"使用此模板生成合同"
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Back, MagicStick, CircleClose, CircleCheck, Delete,
} from '@element-plus/icons-vue'
import { getTemplateDetail, updateTemplateStatus, deleteTemplate } from '@/api/template'
import { useAuthStore } from '@/store/auth'
import {
  TEMPLATE_STATUS_LABELS, TEMPLATE_STATUS_TAG_TYPES, TEMPLATE_STATUS,
} from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isManager = computed(() => authStore.isManager)

const loading = ref(false)
const template = ref(null)

async function fetchDetail() {
  loading.value = true
  try {
    const res = await getTemplateDetail(route.params.id)
    template.value = res.data.template
  } catch (e) {
    // 错误提示由拦截器统一处理
  } finally {
    loading.value = false
  }
}

async function handleToggleStatus() {
  if (!template.value) return
  const target = template.value.status === TEMPLATE_STATUS.ACTIVE
    ? TEMPLATE_STATUS.DISABLED
    : TEMPLATE_STATUS.ACTIVE
  const action = target === TEMPLATE_STATUS.ACTIVE ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(
      `确定要${action}模板"${template.value.name}"吗?`,
      '提示',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await updateTemplateStatus(template.value.id, target)
    ElMessage.success(`已${action}模板`)
    fetchDetail()
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      // 错误提示由拦截器统一处理
    }
  }
}

async function handleDelete() {
  if (!template.value) return
  try {
    await ElMessageBox.confirm(
      `确定要删除模板"${template.value.name}"吗?该操作不可恢复。`,
      '危险操作',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'error' }
    )
    await deleteTemplate(template.value.id)
    ElMessage.success('模板已删除')
    router.push('/templates')
  } catch (e) {
    if (e !== 'cancel' && e?.message) {
      // 错误提示由拦截器统一处理
    }
  }
}

function goGenerate() {
  if (template.value) {
    router.push(`/generation/create?template_id=${template.value.id}`)
  }
}

function goBack() {
  router.push('/templates')
}

function formatTime(t) {
  if (!t) return '-'
  return t.replace('T', ' ').split('.')[0]
}

function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

onMounted(() => {
  fetchDetail()
})
</script>

<style scoped>
.page-container { padding: 0; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.section-card {
  margin-top: 16px;
}
.actions {
  display: flex;
  gap: 12px;
}
</style>
