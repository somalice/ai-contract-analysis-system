/**
 * 招投标管理 API 模块(Sprint 7 - v0.9.0)
 *
 * 对接后端 /api/v1/bids 与 /api/v1/proposals:
 *
 * 招标文件模块(/bids):
 * - POST   /bids/upload            上传招标文件(同步执行 Pipeline)
 * - GET    /bids                   招标文件分页列表
 * - GET    /bids/{id}             招标文件详情(可选 include_text=true)
 * - DELETE /bids/{id}             删除招标文件(需 admin/contract_manager)
 * - POST   /bids/{id}/parse       重新解析招标文件
 * - GET    /bids/{id}/requirement 查询招标需求 15 字段
 * - POST   /bids/{id}/requirement/submit-review  提交需求审核(draft→reviewing)
 * - POST   /bids/{id}/requirement/review         审核需求(reviewing→approved/draft)
 * - PUT    /bids/{id}/requirement/status         通用需求状态变更(调试)
 * - POST   /bids/{id}/generate    生成投标文件(跑 Agent + Word 渲染)
 *
 * 投标生成模块(/proposals):
 * - GET    /proposals              投标生成记录分页列表
 * - GET    /proposals/{id}         生成记录详情(含 sections / trace)
 * - GET    /proposals/{id}/trace   生成记录 Agent Trace
 * - GET    /proposals/{id}/download 下载生成的 Word 文档
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 *
 * 招标文件对象(BidDocument.to_dict()):
 *   {id, bid_no, title, file_info:{name, size, type}, page_count, text_length,
 *    parse_status, extract_method, error_message, uploader, uploader_id,
 *    created_time, updated_time, requirement?:{...}}
 *
 * 招标需求对象(BidRequirement.to_dict()):
 *   {id, requirement_no, bid_document_id, status,
 *    requirement_data:{project_name, tender_org, project_location, budget, deadline,
 *                      duration, delivery_requirements, technical_requirements[],
 *                      qualification_requirements[], scoring_criteria[],
 *                      bid_opening_time, bid_validity, payment_terms, contact, other,
 *                      confidence},
 *    project_name, budget, deadline, field_count, missing_count, confidence,
 *    error_message, created_time, updated_time}
 *
 * 投标生成记录对象(GeneratedProposal.to_dict()):
 *   {id, proposal_no, bid_document_id, status, input_data,
 *    generated_sections:[{section_type, section_name, content, source, references}],
 *    rag_references:[{chunk_id, document_title, page_number, score, ...}],
 *    validation_results:{passed, issues:[{type, description, suggestion, severity}]},
 *    file_info:{name, size},
 *    agent_trace:[{step, thought, decision, action, tool_name, tool_input,
 *                  observation, start_time, end_time, duration_ms, status,
 *                  error_message}],
 *    trace_summary:{steps, total_duration_ms, llm_duration_ms, tool_duration_ms,
 *                   tool_stats, llm_stats, iterations, max_iterations,
 *                   iteration_exceeded},
 *    iterations, llm_error, llm_error_type, error_message, triggered_by,
 *    bid:{id, bid_no, title, parse_status},
 *    started_time, finished_time, created_time, updated_time}
 */
import request from './request'

// ============================================================
// 招标文件模块(/bids)
// ============================================================

/**
 * 上传招标文件(同步执行 Bid Pipeline,耗时 5-30s)
 * @param {FormData} formData 包含 file / title?
 * @param {Function|null} onProgress 上传进度回调
 * @returns {Promise<{bid_document}>}
 */
export function uploadBidDocument(formData, onProgress = null) {
  return request.post('/bids/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000, // Pipeline 同步执行,放宽到 120s
    onUploadProgress: onProgress,
  })
}

/**
 * 招标文件分页列表
 * @param {Object} params {page, size, status?(parse_status), keyword?}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listBidDocuments(params = {}) {
  return request.get('/bids', { params })
}

/**
 * 招标文件详情
 * @param {number|string} id 招标文件 ID
 * @param {boolean} includeText 是否返回全文(默认 false)
 * @returns {Promise<{bid_document}>}
 */
export function getBidDocumentDetail(id, includeText = false) {
  return request.get(`/bids/${id}`, {
    params: includeText ? { include_text: 'true' } : {},
  })
}

/**
 * 删除招标文件(需 admin/contract_manager)
 * @param {number|string} id 招标文件 ID
 * @returns {Promise<{id, bid_no, status}>}
 */
export function deleteBidDocument(id) {
  return request.delete(`/bids/${id}`)
}

/**
 * 重新解析招标文件(LLM 恢复时重试)
 * @param {number|string} id 招标文件 ID
 * @returns {Promise<{bid_document}>}
 */
export function parseBidDocument(id) {
  return request.post(`/bids/${id}/parse`, {}, {
    timeout: 120000, // Pipeline 同步执行,放宽到 120s
  })
}

/**
 * 查询招标需求 15 字段
 * @param {number|string} id 招标文件 ID
 * @returns {Promise<{requirement}>}
 */
export function getBidRequirement(id) {
  return request.get(`/bids/${id}/requirement`)
}

// ============================================================
// 招标需求审核流(Sprint 7.1 - v0.9.1)
// 状态机: draft → reviewing → approved(通过) / draft(驳回)
// Bid Agent 默认仅读取 status='approved' 的需求
// ============================================================

/**
 * 提交需求审核: draft → reviewing
 * @param {number|string} id 招标文件 ID
 * @returns {Promise<{requirement}>} 更新后的需求对象
 */
export function submitRequirementReview(id) {
  return request.post(`/bids/${id}/requirement/submit-review`, {})
}

/**
 * 审核需求: reviewing → approved(通过) / draft(驳回)
 * @param {number|string} id 招标文件 ID
 * @param {boolean} approved true=审核通过, false=驳回
 * @param {string|null} comment 审核意见(驳回时建议填写,后端写入 error_message)
 * @returns {Promise<{requirement}>} 更新后的需求对象
 */
export function reviewRequirement(id, approved, comment = null) {
  const payload = { approved: !!approved }
  if (comment) payload.comment = comment
  return request.post(`/bids/${id}/requirement/review`, payload)
}

/**
 * 更新需求状态(通用状态变更,调试/低级别 API)
 * 后端按 REVIEW_TRANSITIONS 校验,非法跳转返回 400
 * @param {number|string} id 招标文件 ID
 * @param {string} newStatus 目标状态: draft / reviewing / approved
 * @returns {Promise<{requirement}>} 更新后的需求对象
 */
export function updateRequirementStatus(id, newStatus) {
  return request.put(`/bids/${id}/requirement/status`, { new_status: newStatus })
}

/**
 * 生成投标文件(跑 Agent + Word 渲染,耗时 15-90s)
 * @param {number|string} id 招标文件 ID
 * @param {Object|null} inputData 可选输入参数 {company_profile_overrides, options}
 * @returns {Promise<{proposal}>}
 */
export function generateProposal(id, inputData = null) {
  const payload = inputData ? { input_data: inputData } : {}
  return request.post(`/bids/${id}/generate`, payload, {
    timeout: 300000, // Agent + Word 渲染可能 15-90s,放宽到 300s
  })
}

// ============================================================
// 投标生成模块(/proposals)
// ============================================================

/**
 * 投标生成记录分页列表
 * @param {Object} params {page, size, status?, bid_document_id?}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listProposals(params = {}) {
  return request.get('/proposals', { params })
}

/**
 * 投标生成记录详情(含 sections / trace)
 * @param {number|string} id 生成记录 ID
 * @returns {Promise<{proposal}>}
 */
export function getProposalDetail(id) {
  return request.get(`/proposals/${id}`)
}

/**
 * 生成记录 Agent Trace(供前端 Timeline)
 * @param {number|string} id 生成记录 ID
 * @returns {Promise<{trace}>}
 */
export function getProposalTrace(id) {
  return request.get(`/proposals/${id}/trace`)
}

/**
 * 下载生成的投标 Word 文档(返回 Blob)
 * @param {number|string} id 生成记录 ID
 * @returns {Promise<Blob>}
 */
export function downloadProposal(id) {
  return request.get(`/proposals/${id}/download`, {
    responseType: 'blob',
    timeout: 60000,
  })
}
