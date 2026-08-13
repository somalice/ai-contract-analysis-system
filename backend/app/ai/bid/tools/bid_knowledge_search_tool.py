"""
Tool2:招标知识库检索工具(Sprint 7 - v0.9.0)

职责:
- 检索企业知识库(招标规范 / 案例 / 资质 / 企业资料),返回相关片段
- 复用 Sprint 4 retriever + rag_service._build_context_and_references
- 按 knowledge_type 后过滤(批量查表避免 N+1)

任务书要求返回字段:document_title / chunk_id / page_number / score(全部包含)

容错:
- 向量库未初始化 / 检索异常 / 无命中 → 返回空 references,不中断 Agent 循环
- 与 Sprint 5 KnowledgeSearchTool 一致的降级策略

约束:不修改 rag_service / retriever / vectorstore / embedding(只读 import)
镜像:Sprint 5 knowledge_search_tool(增加 knowledge_type 后过滤)
"""
from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.bid.context import ProposalContext
from app.extensions.logger import logger


# ---------- 后过滤的 knowledge_type 白名单 ----------
# 仅保留与投标相关的知识类型(排除 'general' 之外不相关的)
_BID_KNOWLEDGE_TYPES = ('bid', 'case', 'qualification', 'company', 'general')


class BidKnowledgeSearchTool(BaseTool):
    """招标知识库检索工具(RAG TopK + knowledge_type 后过滤)"""

    @property
    def name(self) -> str:
        return 'bid_knowledge_search_tool'

    @property
    def description(self) -> str:
        return (
            '检索企业知识库(招标规范、类似项目案例、资质证书、企业资料),返回与查询最相关的片段。'
            '每个片段含来源文档标题(document_title)、片段ID(chunk_id)、页码(page_number)、'
            '相似度分数(score,0-1,越高越相关)及文本内容。'
            '用于为投标章节生成提供规范参考与案例引用。需提供 query 参数(检索关键词)。'
        )

    @property
    def args_schema(self) -> dict:
        return {
            'query': '检索关键词或问题(必填,如"技术方案编写规范"、"类似项目案例")',
        }

    def run(self, args: dict, ctx: ProposalContext) -> dict:
        """
        检索知识库(按 knowledge_type 后过滤)
        :param args: {query: str}
        :return: {query, references, hit_count, context}
            - references: [{chunk_id, document_id, document_title, document_label,
                            chunk_index, page_number, score, text, knowledge_type}]
            - hit_count: 命中数(过滤后)
            - context: 拼接的上下文文本(带 [文档n] 标注)
        """
        query = args.get('query', '') if args else ''
        if not query or not str(query).strip():
            return {
                'query': '',
                'references': [],
                'hit_count': 0,
                'context': '',
                'error': 'query 不能为空',
            }
        query = str(query).strip()

        # 局部 import(避免模块加载时强依赖 knowledge 层)
        try:
            from app.knowledge.services.vector_store_registry import vector_store_registry
            from app.knowledge.services.rag_service import _build_context_and_references
        except ImportError:
            logger.exception('[Bid:knowledge_search_tool] knowledge 层未启用')
            return {
                'query': query,
                'references': [],
                'hit_count': 0,
                'context': '',
                'error': '知识库模块未启用',
            }

        # 检索
        try:
            retriever = vector_store_registry.retriever
            if retriever is None:
                return {
                    'query': query,
                    'references': [],
                    'hit_count': 0,
                    'context': '',
                    'note': '向量库未初始化,无检索结果',
                }
            retrieval_results = retriever.retrieve(query)
        except Exception:
            logger.exception('[Bid:knowledge_search_tool] 检索失败: query=%s', query[:50])
            return {
                'query': query,
                'references': [],
                'hit_count': 0,
                'context': '',
                'error': '检索服务异常,已降级为空结果',
            }

        # 构建 references(复用 rag_service,只读 import,不修改)
        try:
            context_str, references = _build_context_and_references(retrieval_results)
        except Exception:
            logger.exception('[Bid:knowledge_search_tool] references 构建失败')
            return {
                'query': query,
                'references': [],
                'hit_count': 0,
                'context': '',
                'error': 'references 构建失败',
            }

        # ---------- knowledge_type 后过滤 ----------
        # 批量查 KnowledgeDocument.knowledge_type,建立 id → type 映射(避免 N+1)
        references = self._filter_by_knowledge_type(references)

        logger.info('[Bid:knowledge_search_tool] 检索: query_len=%s hits=%s(过滤后)',
                    len(query), len(references))

        return {
            'query': query,
            'references': references,
            'hit_count': len(references),
            'context': context_str,
        }

    def _filter_by_knowledge_type(self, references: list) -> list:
        """
        按 knowledge_type 后过滤(批量查表避免 N+1)

        :param references: 原始 references 列表(含 document_id)
        :return: 过滤后的 references(仅保留 _BID_KNOWLEDGE_TYPES 中的类型)
        """
        if not references:
            return []

        try:
            from app.models.knowledge_document import KnowledgeDocument
            from app.extensions.db import db
        except ImportError:
            logger.exception('[Bid:knowledge_search_tool] KnowledgeDocument 模型未启用,跳过过滤')
            return references

        # 收集所有 document_id
        doc_ids = list({r.get('document_id') for r in references if r.get('document_id')})
        if not doc_ids:
            return references

        try:
            # 批量查 id → knowledge_type 映射
            docs = db.session.query(
                KnowledgeDocument.id, KnowledgeDocument.knowledge_type
            ).filter(KnowledgeDocument.id.in_(doc_ids)).all()
            type_map = {d[0]: d[1] for d in docs}
        except Exception:
            logger.exception('[Bid:knowledge_search_tool] knowledge_type 查询失败,跳过过滤')
            return references

        # 过滤 + 附加 knowledge_type 字段
        filtered = []
        for ref in references:
            doc_id = ref.get('document_id')
            ktype = type_map.get(doc_id, 'general')
            # 仅保留白名单类型
            if ktype in _BID_KNOWLEDGE_TYPES:
                ref_copy = dict(ref)
                ref_copy['knowledge_type'] = ktype
                filtered.append(ref_copy)

        return filtered
