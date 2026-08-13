/**
 * Prompt 模板管理 API 模块(Sprint 8 - v1.0.0 企业级 AI 增强)
 *
 * 对接后端 /api/v1/prompts:
 * - GET    /prompts                 模板分页列表(支持 name / status 过滤)
 * - GET    /prompts/{id}            模板详情(含 system_prompt / human_prompt)
 * - POST   /prompts                 创建模板(仅 admin)
 * - PUT    /prompts/{id}            更新模板(仅 admin)
 * - POST   /prompts/{id}/activate   激活模板(同 name 其他版本自动 inactive,仅 admin)
 * - DELETE /prompts/{id}            删除模板(active 状态禁止删除,仅 admin)
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 *
 * Prompt 模板对象(PromptTemplate.to_dict()):
 *   {id, name, version, status, description,
 *    created_by, created_by_username, created_time, updated_time,
 *    system_prompt, human_prompt}
 *
 * 权限(后端 role_required):
 * - GET 列表/详情: admin / contract_manager
 * - 创建/更新/激活/删除:仅 admin
 *
 * 约束:
 * - name 必须为 VALID_NAMES 之一(contract_review / contract_generation /
 *   bid_proposal / bid_requirement / rag_answer / contract_extract)
 * - status: active / inactive / draft
 * - 同一 name 仅允许一个 active(后端事务保证)
 */
import request from './request'

/**
 * 模板分页列表
 * @param {Object} params {name?, status?, page?, size?}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listPromptTemplates(params = {}) {
  return request.get('/prompts', { params })
}

/**
 * 模板详情(含 system_prompt / human_prompt 全文)
 * @param {number|string} id 模板 ID
 * @returns {Promise<{template}>}
 */
export function getPromptTemplate(id) {
  return request.get(`/prompts/${id}`)
}

/**
 * 创建模板(仅 admin)
 * @param {Object} data {name, version, system_prompt, human_prompt, description?, status?}
 * @returns {Promise<{template}>}
 */
export function createPromptTemplate(data) {
  return request.post('/prompts', data)
}

/**
 * 更新模板(仅 admin)
 * 可更新字段:system_prompt / human_prompt / description / status / version
 * @param {number|string} id 模板 ID
 * @param {Object} data 待更新字段
 * @returns {Promise<{template}>}
 */
export function updatePromptTemplate(id, data) {
  return request.put(`/prompts/${id}`, data)
}

/**
 * 激活模板(仅 admin)
 * 激活后同 name 其他版本自动置 inactive,后端事务保证唯一 active
 * @param {number|string} id 模板 ID
 * @returns {Promise<{template}>}
 */
export function activatePromptTemplate(id) {
  return request.post(`/prompts/${id}/activate`, {})
}

/**
 * 删除模板(仅 admin)
 * active 状态模板禁止直接删除,需先停用或激活其他版本
 * @param {number|string} id 模板 ID
 * @returns {Promise<{deleted, id}>}
 */
export function deletePromptTemplate(id) {
  return request.delete(`/prompts/${id}`)
}
