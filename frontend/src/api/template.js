/**
 * 合同模板管理 API 模块(Sprint 6 - v0.8.0)
 *
 * 对接后端 /api/v1/templates:
 * - GET    /templates                 模板分页列表(需 JWT)
 * - POST   /templates/upload          上传模板(需 admin/contract_manager)
 * - GET    /templates/{id}            模板详情(含 variables,需 JWT)
 * - PATCH  /templates/{id}/status     启停模板(需 admin/contract_manager)
 * - DELETE /templates/{id}            删除模板(需 admin/contract_manager)
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 *
 * 模板对象(ContractTemplate.to_dict()):
 *   {id, template_no, name, description, contract_type,
 *    file_info:{name, size}, variables:[{name, label, required, sample}],
 *    variable_count, version, status, creator, creator_id,
 *    created_time, updated_time}
 */
import request from './request'

/**
 * 模板分页列表
 * @param {Object} params {page, size, keyword, status, contract_type, version}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listTemplates(params = {}) {
  return request.get('/templates', { params })
}

/**
 * 上传模板(需 admin/contract_manager)
 * @param {FormData} formData 包含 file / name / description / contract_type / version
 * @param {Object} [onProgress] 上传进度回调 {onUploadProgress}
 * @returns {Promise<{template}>}
 */
export function uploadTemplate(formData, onProgress = null) {
  return request.post('/templates/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000, // 上传模板可能较大,放宽到 120s
    onUploadProgress: onProgress,
  })
}

/**
 * 模板详情(含 variables)
 * @param {number|string} id 模板 ID
 * @returns {Promise<{template}>}
 */
export function getTemplateDetail(id) {
  return request.get(`/templates/${id}`)
}

/**
 * 启停模板(需 admin/contract_manager)
 * @param {number|string} id 模板 ID
 * @param {string} status 目标状态 active / disabled
 * @returns {Promise<{template}>}
 */
export function updateTemplateStatus(id, status) {
  return request.patch(`/templates/${id}/status`, { status })
}

/**
 * 删除模板(需 admin/contract_manager)
 * @param {number|string} id 模板 ID
 * @returns {Promise<null>}
 */
export function deleteTemplate(id) {
  return request.delete(`/templates/${id}`)
}
