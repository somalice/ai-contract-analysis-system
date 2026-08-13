/**
 * 合同审核 API 模块(Sprint 5 - v0.7.0 / v0.7.1 增强)
 *
 * 对接后端 /api/v1/contracts 与 /api/v1/reviews:
 * - POST /contracts/{id}/review     触发合同 AI 风险审核(admin/contract_manager)
 * - GET  /contracts/{id}/reviews    合同的审核历史(分页)
 * - GET  /reviews                   全局审核报告列表(分页,供"合同审核"菜单页)
 * - GET  /reviews/{id}              审核报告详情(含 risks / tool_calls_log / agent_trace)
 * - GET  /reviews/{id}/trace        查询 Agent 执行 Trace(v0.7.1 新增,供前端 Timeline)
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 * - 触发审核:data.{review, contract}
 * - 审核历史/全局列表:data.{items, total, page, size}
 * - 审核详情:data.review
 * - Agent Trace:data.trace
 *
 * 审核报告对象(ReviewReport.to_dict()):
 *   {id, review_no, contract_id, task_id, status, risk_level, summary,
 *    risks:[{type, severity, description, suggestion, evidence, references}],
 *    tool_calls_log:[{tool, args, duration_ms, result_summary, error}],
 *    agent_trace:[{step, thought, decision, action, tool_name, tool_input,
 *                  observation, start_time, end_time, duration_ms, status,
 *                  error_message}],                                      // v0.7.1
 *    trace_summary:{steps, total_ms, llm_ms, tool_ms,
 *                   tool_stats, llm_stats},                              // v0.7.1
 *    iterations, llm_error, llm_error_type, error_message, triggered_by,
 *    started_time, finished_time, created_time, updated_time}
 *
 * 风险对象结构:
 *   {type:'付款风险', severity:'high', description:'...', suggestion:'...',
 *    evidence:'...', references:[{chunk_id, document_title, page_number, score, ...}]}
 */
import request from './request'

/**
 * 触发合同 AI 风险审核
 * 同步执行 Agent(ReAct 循环:LLM 决策 + Tool 执行 + RAG 检索),耗时 15–90s
 * @param {number|string} id 合同 ID
 * @returns {Promise<{review, contract}>}
 */
export function triggerContractReview(id) {
  return request.post(`/contracts/${id}/review`, {}, {
    // Agent 同步执行可能 15–90s,放宽到 300s
    timeout: 300000,
  })
}

/**
 * 获取审核报告详情
 * @param {number|string} id 审核 ID
 * @returns {Promise<{review}>}
 */
export function getReviewDetail(id) {
  return request.get(`/reviews/${id}`)
}

/**
 * 全局审核报告列表(分页,供"合同审核"菜单页)
 * @param {Object} params {page, size, risk_level, status}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listReviews(params = {}) {
  return request.get('/reviews', { params })
}

/**
 * 合同的审核历史(分页)
 * @param {number|string} contractId 合同 ID
 * @param {Object} params {page, size}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listContractReviews(contractId, params = {}) {
  return request.get(`/contracts/${contractId}/reviews`, { params })
}

/**
 * 查询审核报告 Agent 执行 Trace(v0.7.1 新增)
 * 供 ReviewDetail 页 Agent 执行过程 Timeline 展示:
 * Thought → Decision → Action → Observation → Duration → Status
 * @param {number|string} id 审核 ID
 * @returns {Promise<{trace}>}
 *   trace: {id, review_no, contract_id, status, risk_level, iterations,
 *           agent_trace:[...], trace_summary:{...},
 *           llm_error, llm_error_type, started_time, finished_time}
 */
export function getReviewTrace(id) {
  return request.get(`/reviews/${id}/trace`)
}

