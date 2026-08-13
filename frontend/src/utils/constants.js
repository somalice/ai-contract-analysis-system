/**
 * 全局常量定义
 *
 * 包含:角色枚举 / 合同状态枚举 / 状态机转换矩阵 / 状态标签映射
 * 与后端 Contract.VALID_STATUSES / STATUS_TRANSITIONS 保持一致
 */

// ---------- 用户角色 ----------
export const ROLES = {
  ADMIN: 'admin',
  CONTRACT_MANAGER: 'contract_manager',
  EMPLOYEE: 'employee',
}

export const ROLE_LABELS = {
  [ROLES.ADMIN]: '管理员',
  [ROLES.CONTRACT_MANAGER]: '合同管理员',
  [ROLES.EMPLOYEE]: '员工',
}

// ---------- 合同生命周期状态 ----------
// 与后端 Contract.VALID_STATUSES 一致(仅 draft/reviewed/archived)
export const CONTRACT_STATUS = {
  DRAFT: 'draft',
  REVIEWED: 'reviewed',
  ARCHIVED: 'archived',
}

// 状态中文标签
export const STATUS_LABELS = {
  [CONTRACT_STATUS.DRAFT]: '草稿',
  [CONTRACT_STATUS.REVIEWED]: '已审核',
  [CONTRACT_STATUS.ARCHIVED]: '已归档',
}

// 状态对应的 el-tag 类型
export const STATUS_TAG_TYPES = {
  [CONTRACT_STATUS.DRAFT]: 'info',
  [CONTRACT_STATUS.REVIEWED]: 'success',
  [CONTRACT_STATUS.ARCHIVED]: 'warning',
}

// 状态机转换矩阵(current → [允许的 target])
// 与后端 Contract.STATUS_TRANSITIONS 一致:单向流转 draft→reviewed→archived
export const STATUS_TRANSITIONS = {
  [CONTRACT_STATUS.DRAFT]: [CONTRACT_STATUS.REVIEWED],
  [CONTRACT_STATUS.REVIEWED]: [CONTRACT_STATUS.ARCHIVED],
  [CONTRACT_STATUS.ARCHIVED]: [],
}

// ---------- AI 分析状态(合同维度,与后端 Contract.analysis_status 一致) ----------
// Sprint 3 新增 'pending':上传后未触发分析
export const ANALYSIS_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  FAILED: 'failed',
}

export const ANALYSIS_STATUS_LABELS = {
  [ANALYSIS_STATUS.PENDING]: '待分析',
  [ANALYSIS_STATUS.PROCESSING]: '分析中',
  [ANALYSIS_STATUS.COMPLETED]: '已完成',
  [ANALYSIS_STATUS.FAILED]: '分析失败',
}

export const ANALYSIS_STATUS_TAG_TYPES = {
  [ANALYSIS_STATUS.PENDING]: 'info',
  [ANALYSIS_STATUS.PROCESSING]: 'warning',
  [ANALYSIS_STATUS.COMPLETED]: 'success',
  [ANALYSIS_STATUS.FAILED]: 'danger',
}

// ---------- 分析任务状态(Sprint 3 - v0.5.0,任务维度) ----------
// 与后端 AnalysisTask.VALID_STATUSES 一致
export const TASK_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCESS: 'success',
  FAILED: 'failed',
}

export const TASK_STATUS_LABELS = {
  [TASK_STATUS.PENDING]: '等待中',
  [TASK_STATUS.RUNNING]: '执行中',
  [TASK_STATUS.SUCCESS]: '成功',
  [TASK_STATUS.FAILED]: '失败',
}

export const TASK_STATUS_TAG_TYPES = {
  [TASK_STATUS.PENDING]: 'info',
  [TASK_STATUS.RUNNING]: 'warning',
  [TASK_STATUS.SUCCESS]: 'success',
  [TASK_STATUS.FAILED]: 'danger',
}

// ---------- Pipeline Stage(Sprint 3 - v0.5.0) ----------
// 与后端 AnalysisTask.VALID_STAGES 一致,顺序固定
export const PIPELINE_STAGES = [
  'extract',
  'ocr',
  'clean',
  'chunk',
  'llm',
  'save',
]

export const STAGE_LABELS = {
  extract: '文本提取',
  ocr: 'OCR 识别',
  clean: '文本清洗',
  chunk: '文本切分',
  llm: 'LLM 解析',
  save: '字段落库',
}

// Stage 执行状态(与后端 StageResult 一致)
export const STAGE_STATUS = {
  SUCCESS: 'success',
  SKIPPED: 'skipped',
  FAILED: 'failed',
}

export const STAGE_STATUS_LABELS = {
  [STAGE_STATUS.SUCCESS]: '成功',
  [STAGE_STATUS.SKIPPED]: '跳过',
  [STAGE_STATUS.FAILED]: '失败',
}

export const STAGE_STATUS_TAG_TYPES = {
  [STAGE_STATUS.SUCCESS]: 'success',
  [STAGE_STATUS.SKIPPED]: 'info',
  [STAGE_STATUS.FAILED]: 'danger',
}

// ---------- 知识文档 Embedding 状态(Sprint 4 - v0.6.0) ----------
// 与后端 KnowledgeDocument.VALID_EMBEDDING_STATUSES 一致
export const EMBEDDING_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  FAILED: 'failed',
}

export const EMBEDDING_STATUS_LABELS = {
  [EMBEDDING_STATUS.PENDING]: '待处理',
  [EMBEDDING_STATUS.PROCESSING]: '处理中',
  [EMBEDDING_STATUS.COMPLETED]: '已向量化',
  [EMBEDDING_STATUS.FAILED]: '处理失败',
}

export const EMBEDDING_STATUS_TAG_TYPES = {
  [EMBEDDING_STATUS.PENDING]: 'info',
  [EMBEDDING_STATUS.PROCESSING]: 'warning',
  [EMBEDDING_STATUS.COMPLETED]: 'success',
  [EMBEDDING_STATUS.FAILED]: 'danger',
}

// ---------- 合同审核任务状态(Sprint 5 - v0.7.0) ----------
// 与后端 ReviewReport.VALID_STATUSES 一致
export const REVIEW_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCESS: 'success',
  FAILED: 'failed',
}

export const REVIEW_STATUS_LABELS = {
  [REVIEW_STATUS.PENDING]: '等待中',
  [REVIEW_STATUS.RUNNING]: '审核中',
  [REVIEW_STATUS.SUCCESS]: '已完成',
  [REVIEW_STATUS.FAILED]: '审核失败',
}

export const REVIEW_STATUS_TAG_TYPES = {
  [REVIEW_STATUS.PENDING]: 'info',
  [REVIEW_STATUS.RUNNING]: 'warning',
  [REVIEW_STATUS.SUCCESS]: 'success',
  [REVIEW_STATUS.FAILED]: 'danger',
}

// ---------- 风险等级(Sprint 5 - v0.7.0) ----------
// 与后端 ReviewReport.VALID_RISK_LEVELS 一致
export const RISK_LEVEL = {
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
  NONE: 'none',
}

export const RISK_LEVEL_LABELS = {
  [RISK_LEVEL.HIGH]: '高风险',
  [RISK_LEVEL.MEDIUM]: '中风险',
  [RISK_LEVEL.LOW]: '低风险',
  [RISK_LEVEL.NONE]: '无风险',
}

export const RISK_LEVEL_TAG_TYPES = {
  [RISK_LEVEL.HIGH]: 'danger',
  [RISK_LEVEL.MEDIUM]: 'warning',
  [RISK_LEVEL.LOW]: 'primary',
  [RISK_LEVEL.NONE]: 'success',
}

// ---------- 风险严重度(单条风险,与后端 risk_rule_tool SEVERITY_* 一致) ----------
export const RISK_SEVERITY = {
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
}

export const RISK_SEVERITY_LABELS = {
  [RISK_SEVERITY.HIGH]: '高',
  [RISK_SEVERITY.MEDIUM]: '中',
  [RISK_SEVERITY.LOW]: '低',
}

export const RISK_SEVERITY_TAG_TYPES = {
  [RISK_SEVERITY.HIGH]: 'danger',
  [RISK_SEVERITY.MEDIUM]: 'warning',
  [RISK_SEVERITY.LOW]: 'info',
}

// 严重度排序权重(用于风险列表按严重度降序展示)
export const RISK_SEVERITY_ORDER = {
  [RISK_SEVERITY.HIGH]: 3,
  [RISK_SEVERITY.MEDIUM]: 2,
  [RISK_SEVERITY.LOW]: 1,
}

// ---------- 合同模板状态(Sprint 6 - v0.8.0) ----------
// 与后端 ContractTemplate.VALID_STATUSES 一致
export const TEMPLATE_STATUS = {
  ACTIVE: 'active',
  DISABLED: 'disabled',
}

export const TEMPLATE_STATUS_LABELS = {
  [TEMPLATE_STATUS.ACTIVE]: '启用',
  [TEMPLATE_STATUS.DISABLED]: '已停用',
}

export const TEMPLATE_STATUS_TAG_TYPES = {
  [TEMPLATE_STATUS.ACTIVE]: 'success',
  [TEMPLATE_STATUS.DISABLED]: 'info',
}

// ---------- 合同生成任务状态(Sprint 6 - v0.8.0) ----------
// 与后端 GeneratedContract.VALID_STATUSES 一致
export const GENERATION_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCESS: 'success',
  FAILED: 'failed',
}

export const GENERATION_STATUS_LABELS = {
  [GENERATION_STATUS.PENDING]: '等待中',
  [GENERATION_STATUS.RUNNING]: '生成中',
  [GENERATION_STATUS.SUCCESS]: '已完成',
  [GENERATION_STATUS.FAILED]: '生成失败',
}

export const GENERATION_STATUS_TAG_TYPES = {
  [GENERATION_STATUS.PENDING]: 'info',
  [GENERATION_STATUS.RUNNING]: 'warning',
  [GENERATION_STATUS.SUCCESS]: 'success',
  [GENERATION_STATUS.FAILED]: 'danger',
}

// ---------- 招标文件解析状态(Sprint 7 - v0.9.0) ----------
// 与后端 BidDocument.VALID_PARSE_STATUSES 一致
export const BID_PARSE_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  SUCCESS: 'success',
  FAILED: 'failed',
}

export const BID_PARSE_STATUS_LABELS = {
  [BID_PARSE_STATUS.PENDING]: '待解析',
  [BID_PARSE_STATUS.PROCESSING]: '解析中',
  [BID_PARSE_STATUS.SUCCESS]: '解析成功',
  [BID_PARSE_STATUS.FAILED]: '解析失败',
}

export const BID_PARSE_STATUS_TAG_TYPES = {
  [BID_PARSE_STATUS.PENDING]: 'info',
  [BID_PARSE_STATUS.PROCESSING]: 'warning',
  [BID_PARSE_STATUS.SUCCESS]: 'success',
  [BID_PARSE_STATUS.FAILED]: 'danger',
}

// ---------- 投标生成任务状态(Sprint 7 - v0.9.0) ----------
// 与后端 GeneratedProposal.VALID_STATUSES 一致
export const PROPOSAL_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCESS: 'success',
  FAILED: 'failed',
}

export const PROPOSAL_STATUS_LABELS = {
  [PROPOSAL_STATUS.PENDING]: '等待中',
  [PROPOSAL_STATUS.RUNNING]: '生成中',
  [PROPOSAL_STATUS.SUCCESS]: '已完成',
  [PROPOSAL_STATUS.FAILED]: '生成失败',
}

export const PROPOSAL_STATUS_TAG_TYPES = {
  [PROPOSAL_STATUS.PENDING]: 'info',
  [PROPOSAL_STATUS.RUNNING]: 'warning',
  [PROPOSAL_STATUS.SUCCESS]: 'success',
  [PROPOSAL_STATUS.FAILED]: 'danger',
}

// ---------- 知识文档类型(Sprint 7 - v0.9.0) ----------
// 与后端 KnowledgeDocument.VALID_KNOWLEDGE_TYPES 一致
export const KNOWLEDGE_TYPE = {
  CONTRACT: 'contract',
  BID: 'bid',
  COMPANY: 'company',
  CASE: 'case',
  QUALIFICATION: 'qualification',
  GENERAL: 'general',
}

export const KNOWLEDGE_TYPE_LABELS = {
  [KNOWLEDGE_TYPE.CONTRACT]: '合同知识',
  [KNOWLEDGE_TYPE.BID]: '招标知识',
  [KNOWLEDGE_TYPE.COMPANY]: '企业资料',
  [KNOWLEDGE_TYPE.CASE]: '案例库',
  [KNOWLEDGE_TYPE.QUALIFICATION]: '资质文件',
  [KNOWLEDGE_TYPE.GENERAL]: '通用',
}

// ---------- 招标需求 15 字段定义(Sprint 7 - v0.9.0) ----------
// 与后端 BidRequirement.REQUIRED_FIELDS 一致,用于需求解析页展示
export const BID_REQUIREMENT_FIELDS = [
  { key: 'project_name', label: '项目名称', type: 'text' },
  { key: 'tender_org', label: '招标单位', type: 'text' },
  { key: 'project_location', label: '项目地点', type: 'text' },
  { key: 'budget', label: '预算金额', type: 'text' },
  { key: 'deadline', label: '投标截止时间', type: 'text' },
  { key: 'duration', label: '工期 / 服务期', type: 'text' },
  { key: 'delivery_requirements', label: '供货范围 / 交货要求', type: 'text' },
  { key: 'technical_requirements', label: '技术要求', type: 'list' },
  { key: 'qualification_requirements', label: '资格要求', type: 'list' },
  { key: 'scoring_criteria', label: '评分标准', type: 'list' },
  { key: 'bid_opening_time', label: '开标时间', type: 'text' },
  { key: 'bid_validity', label: '投标有效期', type: 'text' },
  { key: 'payment_terms', label: '付款条件', type: 'text' },
  { key: 'contact', label: '联系人 / 电话', type: 'text' },
  { key: 'other', label: '其他', type: 'text' },
]

// ---------- 招标需求审核状态(Sprint 7.1 - v0.9.1) ----------
// 与后端 BidRequirement.VALID_STATUSES 一致
// status 状态机: draft → reviewing → approved
//                            └→ draft(驳回重审)
//                 failed(解析失败,不进入审核流)
//                 pending(瞬时态,正常立即转 failed/approved)
// Bid Agent 默认仅读取 status='approved' 的需求
export const REQUIREMENT_STATUS = {
  DRAFT: 'draft',
  REVIEWING: 'reviewing',
  APPROVED: 'approved',
  PENDING: 'pending',
  FAILED: 'failed',
}

// 审核状态中文标签
export const REQUIREMENT_STATUS_LABELS = {
  [REQUIREMENT_STATUS.DRAFT]: '草稿',
  [REQUIREMENT_STATUS.REVIEWING]: '审核中',
  [REQUIREMENT_STATUS.APPROVED]: '已通过',
  [REQUIREMENT_STATUS.PENDING]: '待处理',
  [REQUIREMENT_STATUS.FAILED]: '解析失败',
}

// 审核状态对应的 el-tag 类型
export const REQUIREMENT_STATUS_TAG_TYPES = {
  [REQUIREMENT_STATUS.DRAFT]: 'info',
  [REQUIREMENT_STATUS.REVIEWING]: 'warning',
  [REQUIREMENT_STATUS.APPROVED]: 'success',
  [REQUIREMENT_STATUS.PENDING]: 'info',
  [REQUIREMENT_STATUS.FAILED]: 'danger',
}

// ---------- Prompt 模板状态(Sprint 8 - v1.0.0) ----------
// 与后端 PromptTemplate.VALID_STATUS 一致
// status 状态机: draft → active(激活) / inactive(停用)
// 同一 name 仅允许一个 active(后端事务保证)
// Agent 加载时 DB 优先读取 active 模板,无 active 则回退 .md 文件
export const PROMPT_STATUS = {
  ACTIVE: 'active',
  INACTIVE: 'inactive',
  DRAFT: 'draft',
}

// Prompt 状态中文标签
export const PROMPT_STATUS_LABELS = {
  [PROMPT_STATUS.ACTIVE]: '已激活',
  [PROMPT_STATUS.INACTIVE]: '已停用',
  [PROMPT_STATUS.DRAFT]: '草稿',
}

// Prompt 状态对应的 el-tag 类型(active 高亮绿色,便于一眼识别生效版本)
export const PROMPT_STATUS_TAG_TYPES = {
  [PROMPT_STATUS.ACTIVE]: 'success',
  [PROMPT_STATUS.INACTIVE]: 'info',
  [PROMPT_STATUS.DRAFT]: 'warning',
}

// ---------- Prompt 模板名称枚举(Sprint 8 - v1.0.0) ----------
// 与后端 PromptTemplate.VALID_NAMES 一致,创建模板时 name 必须在此枚举内
// 后端 _validate_name 校验,非法 name 返回 400
export const PROMPT_NAMES = {
  CONTRACT_REVIEW: 'contract_review',
  CONTRACT_GENERATION: 'contract_generation',
  BID_PROPOSAL: 'bid_proposal',
  BID_REQUIREMENT: 'bid_requirement',
  RAG_ANSWER: 'rag_answer',
  CONTRACT_EXTRACT: 'contract_extract',
}

// Prompt 名称中文标签(用于创建表单 select / 列表展示)
export const PROMPT_NAME_LABELS = {
  [PROMPT_NAMES.CONTRACT_REVIEW]: '合同审核 Agent',
  [PROMPT_NAMES.CONTRACT_GENERATION]: '合同生成 Agent',
  [PROMPT_NAMES.BID_PROPOSAL]: '投标生成 Agent',
  [PROMPT_NAMES.BID_REQUIREMENT]: '招标需求解析',
  [PROMPT_NAMES.RAG_ANSWER]: 'RAG 问答',
  [PROMPT_NAMES.CONTRACT_EXTRACT]: '合同字段提取',
}

// ---------- 操作日志状态(Sprint 8 - v1.0.0) ----------
// 与后端 OperationLog.status 一致:success / failed
export const LOG_STATUS = {
  SUCCESS: 'success',
  FAILED: 'failed',
}

export const LOG_STATUS_LABELS = {
  [LOG_STATUS.SUCCESS]: '成功',
  [LOG_STATUS.FAILED]: '失败',
}

export const LOG_STATUS_TAG_TYPES = {
  [LOG_STATUS.SUCCESS]: 'success',
  [LOG_STATUS.FAILED]: 'danger',
}

// ---------- 操作日志类型枚举(Sprint 8 - v1.0.0) ----------
// 与后端 OperationLog.VALID_OPERATION_TYPES 一致
export const OPERATION_TYPES = {
  USER_LOGIN: 'user_login',
  CONTRACT_UPLOAD: 'contract_upload',
  CONTRACT_ANALYSIS: 'contract_analysis',
  CONTRACT_REVIEW: 'contract_review',
  CONTRACT_GENERATE_PREVIEW: 'contract_generate_preview',
  CONTRACT_GENERATE: 'contract_generate',
  KNOWLEDGE_UPLOAD: 'knowledge_upload',
  KNOWLEDGE_DELETE: 'knowledge_delete',
  KNOWLEDGE_SEARCH: 'knowledge_search',
  BID_UPLOAD: 'bid_upload',
  BID_PARSE: 'bid_parse',
  BID_REQUIREMENT_SUBMIT: 'bid_requirement_submit',
  BID_REQUIREMENT_REVIEW: 'bid_requirement_review',
  BID_GENERATE: 'bid_generate',
  TEMPLATE_UPLOAD: 'template_upload',
  TEMPLATE_DELETE: 'template_delete',
  PROMPT_CREATE: 'prompt_create',
  PROMPT_UPDATE: 'prompt_update',
  PROMPT_ACTIVATE: 'prompt_activate',
  PROMPT_DELETE: 'prompt_delete',
  EVALUATION_GENERATE: 'evaluation_generate',
}

// 操作类型中文标签(用于筛选下拉框 / 列表展示)
export const OPERATION_TYPE_LABELS = {
  [OPERATION_TYPES.USER_LOGIN]: '用户登录',
  [OPERATION_TYPES.CONTRACT_UPLOAD]: '合同上传',
  [OPERATION_TYPES.CONTRACT_ANALYSIS]: '合同解析',
  [OPERATION_TYPES.CONTRACT_REVIEW]: '合同审核',
  [OPERATION_TYPES.CONTRACT_GENERATE_PREVIEW]: '合同生成预览',
  [OPERATION_TYPES.CONTRACT_GENERATE]: '合同生成',
  [OPERATION_TYPES.KNOWLEDGE_UPLOAD]: '知识上传',
  [OPERATION_TYPES.KNOWLEDGE_DELETE]: '知识删除',
  [OPERATION_TYPES.KNOWLEDGE_SEARCH]: '知识搜索',
  [OPERATION_TYPES.BID_UPLOAD]: '招标上传',
  [OPERATION_TYPES.BID_PARSE]: '招标解析',
  [OPERATION_TYPES.BID_REQUIREMENT_SUBMIT]: '需求提交审核',
  [OPERATION_TYPES.BID_REQUIREMENT_REVIEW]: '需求审核',
  [OPERATION_TYPES.BID_GENERATE]: '投标生成',
  [OPERATION_TYPES.TEMPLATE_UPLOAD]: '模板上传',
  [OPERATION_TYPES.TEMPLATE_DELETE]: '模板删除',
  [OPERATION_TYPES.PROMPT_CREATE]: 'Prompt 创建',
  [OPERATION_TYPES.PROMPT_UPDATE]: 'Prompt 更新',
  [OPERATION_TYPES.PROMPT_ACTIVATE]: 'Prompt 激活',
  [OPERATION_TYPES.PROMPT_DELETE]: 'Prompt 删除',
  [OPERATION_TYPES.EVALUATION_GENERATE]: 'AI 评估生成',
}

// ---------- 操作目标类型标签(用于详情展示) ----------
export const TARGET_TYPE_LABELS = {
  contract: '合同',
  review: '审核报告',
  generation: '生成记录',
  proposal: '投标文件',
  knowledge: '知识文档',
  bid: '招标文件',
  template: '合同模板',
  prompt: 'Prompt 模板',
  evaluation: 'AI 评估',
}

// ---------- AI Agent 类型枚举(Sprint 8 - v1.0.0) ----------
// 与后端 AIRequestLog.VALID_AGENT_TYPES 一致
export const AI_AGENT_TYPES = {
  CONTRACT_REVIEW: 'contract_review',
  GENERATION: 'generation',
  BID: 'bid',
  RAG: 'rag',
}

// Agent 类型中文标签
export const AI_AGENT_TYPE_LABELS = {
  [AI_AGENT_TYPES.CONTRACT_REVIEW]: '合同审核 Agent',
  [AI_AGENT_TYPES.GENERATION]: '合同生成 Agent',
  [AI_AGENT_TYPES.BID]: '投标生成 Agent',
  [AI_AGENT_TYPES.RAG]: 'RAG 问答',
}

// ---------- 系统版本 ----------
export const APP_VERSION = 'v1.0.0'

// ---------- localStorage 键名 ----------
export const STORAGE_KEYS = {
  TOKEN: 'admin_token',
  USER: 'admin_user',
}
