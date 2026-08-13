/**
 * 合同管理 API 模块(Phase B / Sprint 3 扩展)
 *
 * 对接后端 /api/v1/contracts:
 * - POST   /contracts/upload          上传合同(multipart/form-data)
 * - GET    /contracts                  合同分页列表
 * - GET    /contracts/{id}             合同详情
 * - PATCH  /contracts/{id}/status      更新合同状态(状态机)
 * - POST   /contracts/{id}/analysis   触发 AI 分析(Sprint 3)
 * - GET    /contracts/{id}/fields      获取合同字段(Sprint 3)
 *
 * 对接后端 /api/v1/analysis(Sprint 3):
 * - GET    /analysis/{task_id}         查询分析任务状态
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 * - 上传/详情/状态更新:data.contract
 * - 列表:data.{items, total, page, size}
 * - 触发分析:data.{task, contract}
 * - 获取字段:data.{fields, task, source}
 * - 查询任务:data.task
 *
 * 合同对象结构(Contract.to_dict()):
 *   {id, contract_no, title, contract_type, description, status,
 *    file_info:{name,size}, analysis_status, analysis_result,
 *    creator:{id,username,role,...}, creator_id, created_time, updated_time}
 *
 * 分析任务对象(AnalysisTask.to_dict()):
 *   {id, task_no, contract_id, document_id, status, current_stage,
 *    stages_log:[{stage,status,duration_ms,error,metadata}],
 *    error_message, started_time, finished_time, ...}
 */
import request from './request'

/**
 * 上传合同
 * @param {FormData} formData 包含 file / contract_type / title / description
 * @returns {Promise<{contract}>}
 */
export function uploadContract(formData) {
  return request.post('/contracts/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    // Sprint 3:上传不再含 AI 分析,缩短超时到 60s
    timeout: 60000,
  })
}

/**
 * 合同分页列表
 * @param {Object} params {page, size, keyword, status, creator_id}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listContracts(params = {}) {
  return request.get('/contracts', { params })
}

/**
 * 合同详情
 * @param {number|string} id 合同 ID
 * @returns {Promise<{contract}>}
 */
export function getContractDetail(id) {
  return request.get(`/contracts/${id}`)
}

/**
 * 更新合同状态(状态机:draft → reviewed → archived)
 * @param {number|string} id 合同 ID
 * @param {string} status 目标状态
 * @returns {Promise<{contract}>}
 */
export function updateContractStatus(id, status) {
  return request.patch(`/contracts/${id}/status`, { status })
}

// ============================================================
// Sprint 3 - v0.5.0:Document Pipeline AI 解析接口
// ============================================================

/**
 * 触发合同 AI 分析
 * 同步执行 Pipeline(extract → ocr → clean → chunk → llm → save),耗时较长
 * @param {number|string} id 合同 ID
 * @returns {Promise<{task, contract}>}
 */
export function triggerContractAnalysis(id) {
  return request.post(`/contracts/${id}/analysis`, {}, {
    // Pipeline 同步执行可能 10–60s,放宽到 300s
    timeout: 300000,
  })
}

/**
 * 查询分析任务状态
 * @param {number|string} taskId 任务 ID
 * @returns {Promise<{task}>}
 */
export function getAnalysisTask(taskId) {
  return request.get(`/analysis/${taskId}`)
}

/**
 * 获取合同字段
 * @param {number|string} id 合同 ID
 * @returns {Promise<{fields, task, source}>}
 */
export function getContractFields(id) {
  return request.get(`/contracts/${id}/fields`)
}
