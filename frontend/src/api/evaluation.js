/**
 * AI 评估 API 模块(Sprint 8.5 - v1.0.0 封版前 AI 评估)
 *
 * 对接后端 /api/v1/evaluation:
 * - GET  /evaluation/summary        最新评估 summary(PASS/PENDING/FAIL 三态 + RAG 4 指标 + AI 稳定性)
 * - GET  /evaluation/history        历史评估快照列表(精简字段)
 * - GET  /evaluation/history/{id}   历史快照详情(完整 metrics)
 * - POST /evaluation/run            执行一次完整评估(admin)
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 *
 * summary 结构(backend/app/evaluation/metrics/status_judge.build_summary):
 *   {
 *     version, generated_at,
 *     total_questions, context_hit_count, context_hit_rate,
 *     faithfulness, answer_relevancy, context_precision, context_recall,
 *     ai_total_calls, ai_success_rate, ai_p95_latency_ms,
 *     total_tokens, estimated_cost_rmb,
 *     agent_task_total, agent_completion_rate, tool_call_total, tool_success_rate,
 *     test_environment: { knowledge_total_documents, knowledge_hit_documents, ... },
 *     status: 'PASS'|'PENDING'|'FAIL', status_label, reason,
 *     rag_status: {...}, ai_status: {...},
 *     rag_aggregate, rag_per_category, ai_per_agent, agent_tool_breakdown
 *   }
 *
 * 权限(后端 role_required):
 * - 所有评估接口仅 admin 可访问
 */
import request from './request'

/**
 * 获取最新评估 summary
 * @returns {Promise<Object>} summary 结构(见文件头注释)
 */
export function getEvaluationSummary() {
  return request.get('/evaluation/summary')
}

/**
 * 历史评估快照列表
 * @param {Object} params {page?, size?}
 * @returns {Promise<{total, page, size, items}>}
 */
export function listEvaluationHistory(params = {}) {
  return request.get('/evaluation/history', { params })
}

/**
 * 历史快照详情(完整 metrics)
 * @param {number|string} id 快照 ID
 * @returns {Promise<Object>} EvaluationReport.to_dict(include_metrics=true)
 */
export function getEvaluationHistoryDetail(id) {
  return request.get(`/evaluation/history/${id}`)
}

/**
 * 执行一次完整 AI 评估(仅 admin) - Sprint 8.6.1 异步化
 *
 * 立即返回(不阻塞,HTTP 202):
 * {
 *   task_id: "EVALTASK-...",
 *   status: "pending",            // 随后后台置 running
 *   progress: 0,
 *   stage: "creating",
 *   evaluation_mode: "quick|standard|full",
 *   sample_size: 10, use_llm_answer: false
 * }
 * 前端需轮询 getEvaluationTask(task_id) 获取实时进度,success 后刷新 summary。
 * @param {Object} data
 *   { mode?: 'quick'|'standard'|'full', sample_size?, use_llm_answer?, period_days? }
 * @returns {Promise<Object>} 任务 dict
 */
export function runEvaluation(data = {}) {
  return request.post('/evaluation/run', data, { timeout: 30000 })
}

/**
 * 查询评估异步任务状态(Sprint 8.6.1,前端轮询进度用)
 * @param {string} taskId 任务编号
 * @returns {Promise<Object>}
 *   { task_id, status, progress, stage, report_id, error, start_time, end_time,
 *     evaluation_mode, sample_size, use_llm_answer }
 */
export function getEvaluationTask(taskId) {
  return request.get(`/evaluation/task/${taskId}`)
}
