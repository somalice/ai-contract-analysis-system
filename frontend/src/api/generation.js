/**
 * 合同生成 API 模块(Sprint 6 - v0.8.0)
 *
 * 对接后端 /api/v1/generation 与 /api/v1/generated:
 * - POST /generation/preview           预览生成结果(跑 Agent,不渲染 Word)
 * - POST /generation/generate          正式生成合同(跑 Agent + 渲染 Word + 建合同)
 * - GET  /generation/history           生成记录分页列表
 * - GET  /generation/{id}              生成记录详情(含 clauses / trace)
 * - GET  /generation/{id}/trace        生成记录 Agent Trace(供前端 Timeline)
 * - GET  /generated/{id}/download      下载生成的 Word 文档
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 *
 * 生成记录对象(GeneratedContract.to_dict()):
 *   {id, generation_no, template_id, contract_id, status,
 *    input_variables, generated_clauses:[{name, content, source, references}],
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
 *    template:{id, name, template_no, contract_type},
 *    contract:{id, contract_no, title, status},
 *    started_time, finished_time, created_time, updated_time}
 */
import request from './request'

/**
 * 预览生成结果(跑 Agent,不渲染 Word,不建合同)
 * 同步执行 Agent(ReAct 循环),耗时 5–30s
 * @param {Object} payload {template_id, input_variables, contract_type?}
 * @returns {Promise<{generation}>}
 */
export function previewGeneration(payload) {
  return request.post('/generation/preview', payload, {
    timeout: 120000, // Agent 同步执行可能较慢,放宽到 120s
  })
}

/**
 * 正式生成合同(跑 Agent + 渲染 Word + 建合同)
 * 同步执行 Agent + Word 渲染,耗时 15–90s
 * @param {Object} payload {template_id, input_variables, contract_type?, title?, description?}
 * @returns {Promise<{generation, contract}>}
 */
export function generateContract(payload) {
  return request.post('/generation/generate', payload, {
    timeout: 300000, // Agent + Word 渲染可能 15–90s,放宽到 300s
  })
}

/**
 * 生成记录分页列表
 * @param {Object} params {page, size, status?, template_id?}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listGenerations(params = {}) {
  return request.get('/generation/history', { params })
}

/**
 * 生成记录详情(含 clauses / trace)
 * @param {number|string} id 生成记录 ID
 * @returns {Promise<{generation}>}
 */
export function getGenerationDetail(id) {
  return request.get(`/generation/${id}`)
}

/**
 * 生成记录 Agent Trace(供前端 Timeline 展示)
 * @param {number|string} id 生成记录 ID
 * @returns {Promise<{trace}>}
 */
export function getGenerationTrace(id) {
  return request.get(`/generation/${id}/trace`)
}

/**
 * 下载生成的 Word 文档(返回 Blob)
 * @param {number|string} id 生成记录 ID
 * @returns {Promise<Blob>}
 */
export function downloadGeneratedContract(id) {
  return request.get(`/generated/${id}/download`, {
    responseType: 'blob',
    timeout: 60000,
  })
}
