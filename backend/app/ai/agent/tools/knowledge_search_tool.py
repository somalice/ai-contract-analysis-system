"""
Tool2:知识库检索工具(Sprint 5 - v0.7.0)

职责:
- 检索合同知识库(法规 / 规范 / 历史合同),返回相关条款片段及来源
- 只读复用 Sprint 4 的 vector_store_registry.retriever + rag_service._build_context_and_references

任务书要求返回字段:document_title / chunk_id / page_number / score(全部包含)

容错:
- 向量库未初始化 / 检索异常 / 无命中 → 返回空 references,不中断 Agent 循环
- 符合 Sprint 4 Final Review §6.2 第 4 点(空知识库 / 无命中降级)

约束:不修改 rag_service / retriever / vectorstore / embedding(只读 import)
"""
from app.ai.agent.context import AgentContext
from app.ai.agent.tools.base import BaseTool
from app.extensions.logger import logger


class KnowledgeSearchTool(BaseTool):
    """知识库检索工具(RAG TopK + 阈值,返回 references)"""

    @property
    def name(self) -> str:
        return 'knowledge_search_tool'

    @property
    def description(self) -> str:
        return (
            '检索合同知识库(企业合同规范、法规、历史合同),返回与查询最相关的条款片段。'
            '每个片段含来源文档标题(document_title)、片段ID(chunk_id)、页码(page_number)、'
            '相似度分数(score,0-1,越高越相关)及文本内容。'
            '用于为风险报告提供知识依据与参考来源。需提供 query 参数(检索关键词)。'
        )

    @property
    def args_schema(self) -> dict:
        return {
            'query': '检索关键词或问题(必填,如"付款周期规范"、"违约责任条款")',
        }

    def run(self, args: dict, ctx: AgentContext) -> dict:
        """
        检索知识库
        :param args: {query: str}
        :return: {query, references, hit_count, context}
            - references: [{chunk_id, document_id, document_title, document_label,
                            chunk_index, page_number, score, text}]
            - hit_count: 命中数
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

        # 局部 import(避免模块加载时强依赖 knowledge 层,支持 knowledge 未启用场景)
        try:
            from app.knowledge.services.vector_store_registry import vector_store_registry
            from app.knowledge.services.rag_service import _build_context_and_references
        except ImportError:
            logger.exception('[Agent:knowledge_search_tool] knowledge 层未启用')
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
            logger.exception('[Agent:knowledge_search_tool] 检索失败: query=%s', query[:50])
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
            logger.exception('[Agent:knowledge_search_tool] references 构建失败')
            return {
                'query': query,
                'references': [],
                'hit_count': 0,
                'context': '',
                'error': 'references 构建失败',
            }

        logger.info('[Agent:knowledge_search_tool] 检索: query_len=%s hits=%s',
                    len(query), len(references))

        return {
            'query': query,
            'references': references,
            'hit_count': len(references),
            'context': context_str,
        }
