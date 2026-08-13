/**
 * 系统日志 API 模块(Sprint 8 - v1.0.0 企业级 AI 增强)
 *
 * 对接后端 /api/v1/logs:
 * - GET /logs/operations         操作审计日志分页列表
 * - GET /logs/operations/{id}    操作日志详情
 * - GET /logs/ai                 AI 调用日志分页列表
 * - GET /logs/ai/{id}            AI 日志详情
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 *
 * 权限(后端 role_required):
 * - 所有日志接口仅 admin 可访问
 *
 * OperationLog.to_dict() 字段:
 *   {id, user_id, username, operation_type, target_type, target_id,
 *    method, path, status, status_code, duration_ms, ip_address,
 *    detail(JSON), error_message, created_time}
 *
 * AIRequestLog.to_dict() 字段:
 *   {id, user_id, username, agent_type, model, prompt_version,
 *    input_tokens, output_tokens, total_tokens, latency_ms,
 *    status, error_message, related_id, related_type,
 *    created_time, trace_summary(JSON)}
 *
 * 分页结构:{total, page, size, items:[...]}
 */
import request from './request'

// ---------- 操作审计日志 ----------

/**
 * 操作日志分页列表
 * @param {Object} params 查询参数
 *   - user_id?:        用户 ID 筛选
 *   - operation_type?: 操作类型筛选(user_login / contract_upload 等)
 *   - status?:         状态筛选(success / failed)
 *   - target_type?:    目标类型筛选(contract / review / knowledge 等)
 *   - start_time?:     起始时间(YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
 *   - end_time?:       结束时间
 *   - page?:           页码(默认 1)
 *   - size?:           每页条数(默认 20)
 * @returns {Promise<{total, page, size, items}>}
 */
export function listOperationLogs(params = {}) {
  return request.get('/logs/operations', { params })
}

/**
 * 操作日志详情
 * @param {number|string} id 日志 ID
 * @returns {Promise<Object>} OperationLog.to_dict()
 */
export function getOperationLog(id) {
  return request.get(`/logs/operations/${id}`)
}

// ---------- AI 调用日志 ----------

/**
 * AI 调用日志分页列表
 * @param {Object} params 查询参数
 *   - agent_type?: Agent 类型筛选(contract_review / generation / bid / rag)
 *   - status?:     状态筛选(success / failed)
 *   - user_id?:    用户 ID 筛选
 *   - start_time?: 起始时间
 *   - end_time?:   结束时间
 *   - page?:       页码(默认 1)
 *   - size?:       每页条数(默认 20)
 * @returns {Promise<{total, page, size, items}>}
 */
export function listAiLogs(params = {}) {
  return request.get('/logs/ai', { params })
}

/**
 * AI 日志详情(含 trace_summary)
 * @param {number|string} id 日志 ID
 * @returns {Promise<Object>} AIRequestLog.to_dict(include_trace_summary=True)
 */
export function getAiLog(id) {
  return request.get(`/logs/ai/${id}`)
}
