/**
 * 知识库 & RAG API 模块(Sprint 4 - v0.6.0)
 *
 * 对接后端 /api/v1/knowledge:
 * - POST   /knowledge/upload          上传知识文档(multipart/form-data)
 * - GET    /knowledge                  知识文档分页列表
 * - GET    /knowledge/{id}             知识文档详情(含 chunks 概要)
 * - DELETE /knowledge/{id}             删除知识文档(软删 + 移除向量)
 *
 * 对接后端 /api/v1/rag:
 * - POST   /rag/query                  RAG 检索 + DeepSeek 问答
 *
 * 后端统一响应:{code:200, message:"...", data:{...}}
 * - 上传/详情/删除:data.document / data.{id,doc_no,status}
 * - 列表:data.{items, total, page, size}
 * - RAG 问答:data.{answer, references, hit_count, retrieval_scores, llm_error}
 *
 * 知识文档对象(KnowledgeDocument.to_dict()):
 *   {id, doc_no, title, source_type,
 *    file_info:{name,size,type}, page_count, text_length, chunk_count,
 *    embedding_status, vector_indexed,
 *    uploader:{id,username,role}, uploader_id, status, error_message,
 *    created_time, updated_time,
 *    chunks_preview:[{id, document_id, chunk_index, page_number,
 *                     start_offset, end_offset, token_count, text, metadata,
 *                     vector_id, created_time}]}
 *
 * RAG references 对象:
 *   [{chunk_id, document_id, document_title, document_label,
 *     chunk_index, page_number, score, text}]
 */
import request from './request'

// ============================================================
// 知识库
// ============================================================

/**
 * 上传知识文档
 * 同步执行:保存 → 解析 → chunk → embedding → FAISS → 持久化
 * @param {FormData} formData 包含 file / title
 * @returns {Promise<{document}>}
 */
export function uploadKnowledgeDocument(formData) {
  return request.post('/knowledge/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    // 含解析 + chunk + embedding + FAISS 入库,首次还会下载 embedding 模型,放宽到 300s
    timeout: 300000,
  })
}

/**
 * 知识文档分页列表
 * @param {Object} params {page, size, keyword, embedding_status}
 * @returns {Promise<{items, total, page, size}>}
 */
export function listKnowledgeDocuments(params = {}) {
  return request.get('/knowledge', { params })
}

/**
 * 知识文档详情(含前 3 个 chunk 预览)
 * @param {number|string} id 文档 ID
 * @returns {Promise<{document}>}
 */
export function getKnowledgeDocumentDetail(id) {
  return request.get(`/knowledge/${id}`)
}

/**
 * 删除知识文档(软删 + 从 FAISS 移除向量)
 * @param {number|string} id 文档 ID
 * @returns {Promise<{id, doc_no, status}>}
 */
export function deleteKnowledgeDocument(id) {
  return request.delete(`/knowledge/${id}`)
}

// ============================================================
// RAG 问答
// ============================================================

/**
 * RAG 问答:query → 检索 → DeepSeek → Answer + References
 * 同步执行,检索 + LLM 可能耗时 5–30s
 * @param {string} query 用户问题
 * @returns {Promise<{answer, references, hit_count, retrieval_scores, llm_error}>}
 */
export function queryRag(query) {
  return request.post('/rag/query', { query }, {
    timeout: 120000,
  })
}
