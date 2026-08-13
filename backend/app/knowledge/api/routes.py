"""
知识库 & RAG API(Blueprint)- Sprint 4 v0.6.0

接口:

知识库管理(前缀 /api/v1/knowledge):
- POST   /knowledge/upload         上传知识文档(需 admin/contract_manager)
- GET    /knowledge                知识文档分页列表(需 JWT)
- GET    /knowledge/{id}           知识文档详情(需 JWT)
- DELETE /knowledge/{id}           删除知识文档(需 admin/contract_manager)

RAG 问答(前缀 /api/v1/rag):
- POST   /rag/query                RAG 检索 + DeepSeek 问答(需 JWT)

职责:
- 参数接收与校验
- 调用 knowledge_service / rag_service
- 返回统一 Response

禁止:
- API 层直接访问数据库
- API 层直接调用 Embedding / VectorStore / Retriever / DeepSeek
- API 层写业务逻辑(均下沉至 service)
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.knowledge.services import (
    knowledge_service,
    rag_service,
)
from app.utils.response import success
from app.utils.exceptions import ValidationError
from app.decorators.role_required import role_required


# ============================================================
# 知识库管理 Blueprint
# ============================================================
knowledge_bp = Blueprint('knowledge', __name__)


def _get_current_user():
    """
    从 JWT 提取当前用户信息
    :return: dict {'id': int, 'role': str, 'username': str}
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    return {
        'id': user_id,
        'role': claims.get('role'),
        'username': claims.get('username'),
    }


@knowledge_bp.route('/upload', methods=['POST'])
@role_required('admin', 'contract_manager')
def upload_knowledge_document():
    """
    上传知识文档(需 admin / contract_manager)

    请求:multipart/form-data
      - file: 知识文档(必填,pdf/docx/txt)
      - title: 文档标题(可选,默认取文件名去扩展名)

    流程:保存 → 解析 → chunk → embedding → FAISS → 持久化
    响应:data.document 知识文档信息(含 embedding_status / chunk_count)
    """
    if 'file' not in request.files:
        raise ValidationError('未选择文件')
    file = request.files['file']
    if not file.filename:
        raise ValidationError('文件名为空')

    title = request.form.get('title') or None
    current_user = _get_current_user()

    document = knowledge_service.upload_knowledge_document(
        file, current_user, title=title
    )
    status = document.get('embedding_status')
    message = '上传成功,Embedding 已完成' if status == 'completed' \
        else '上传完成,但 Embedding 失败(文档与 Chunk 已保存)'
    return success(data={'document': document}, message=message)


@knowledge_bp.route('', methods=['GET'])
@jwt_required()
def list_knowledge_documents():
    """
    知识文档分页列表(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)
      - keyword: 关键字(title / doc_no 模糊)
      - embedding_status: 状态过滤(pending/processing/completed/failed)

    返回:{items, total, page, size}
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    keyword = request.args.get('keyword') or None
    embedding_status = request.args.get('embedding_status') or None

    current_user = _get_current_user()
    result = knowledge_service.get_knowledge_document_list(
        page=page, size=size, keyword=keyword,
        embedding_status=embedding_status, current_user=current_user
    )
    return success(data=result)


@knowledge_bp.route('/<int:document_id>', methods=['GET'])
@jwt_required()
def get_knowledge_document(document_id):
    """
    知识文档详情(需 JWT)

    返回:文档信息 + chunks 概要(前 3 个 chunk 预览)
    """
    current_user = _get_current_user()
    document = knowledge_service.get_knowledge_document_detail(document_id, current_user)
    return success(data={'document': document})


@knowledge_bp.route('/<int:document_id>', methods=['DELETE'])
@role_required('admin', 'contract_manager')
def delete_knowledge_document(document_id):
    """
    删除知识文档(需 admin / contract_manager)

    流程:从 FAISS 移除向量 → 软删(status=deleted)
    """
    current_user = _get_current_user()
    result = knowledge_service.delete_knowledge_document(document_id, current_user)
    return success(data=result, message='删除成功')


# ============================================================
# RAG 问答 Blueprint
# ============================================================
rag_bp = Blueprint('rag', __name__)


@rag_bp.route('/query', methods=['POST'])
@jwt_required()
def rag_query():
    """
    RAG 问答(需 JWT)

    请求:application/json
      { "query": "付款违约条款如何约定?" }

    流程:query → 检索(TopK + 阈值)→ 关联 chunk 文本 → DeepSeek 生成回答
    响应:
      - data.answer: 回答文本
      - data.references: 命中 chunk 列表 [{chunk_id, document_id, document_title,
        document_label, chunk_index, page_number, score, text}]
      - data.hit_count: 命中数
      - data.retrieval_scores: 分数列表
      - data.llm_error: LLM 错误信息(成功为 null)

    注意:
    - 空知识库 / 无命中 → answer="未找到相关内容",不调用 LLM
    - DeepSeek 失败 → 仍返回 references,answer 标注失败原因
    - 本接口同步执行,检索 + LLM 可能耗时 5–30s
    """
    data = request.get_json(silent=True) or {}
    query = data.get('query', '')
    if not query or not str(query).strip():
        raise ValidationError('查询问题不能为空')

    current_user = _get_current_user()
    result = rag_service.query_rag(str(query), current_user)
    return success(data=result)
