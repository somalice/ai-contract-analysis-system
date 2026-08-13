"""
稠密检索器(Sprint 4 - v0.6.0)

职责:
- TopK 检索 + Score Threshold 过滤
- 预留 Hybrid Search 扩展(本类为 Dense,未来可新增 HybridRetriever 不改 service)

设计:
- 用 Embedding 将 query 向量化 → VectorStore.search → 过滤阈值 → 关联 chunk_id
- chunk_id 通过 VectorStore.get_chunk_id 获取(不直接查 DB,保持解耦)

解耦:
- VectorStore / Embedding 均通过构造函数注入,不 import 具体类
"""
from typing import List, Optional

from app.extensions.logger import logger
from app.knowledge.vectorstore.base import BaseVectorStore
from app.knowledge.embedding.base import BaseEmbedding
from .base import BaseRetriever, RetrievalResult


class DenseRetriever(BaseRetriever):
    """稠密检索(TopK + Score Threshold)"""

    def __init__(self, vectorstore: BaseVectorStore, embedding: BaseEmbedding,
                 top_k: int = 5, score_threshold: float = 0.35):
        if top_k <= 0:
            raise ValueError('top_k 必须大于 0')
        if not (0.0 <= score_threshold <= 1.0):
            raise ValueError('score_threshold 必须在 [0, 1]')
        self.vectorstore = vectorstore
        self.embedding = embedding
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[RetrievalResult]:
        """
        检索:query → 向量 → TopK → 阈值过滤 → 关联 chunk_id

        :param query: 查询文本
        :param top_k: 可选 TopK 覆盖(Sprint 8.6:供 rerank 召回阶段取更多候选);
            None 时用 self.top_k(原行为,向后兼容)
        :return: list[RetrievalResult],按 score 降序
        """
        if not query or not query.strip():
            return []

        if self.vectorstore.size == 0:
            logger.info('[Knowledge:retriever] 向量库为空,跳过检索')
            return []

        # Sprint 8.6: 支持调用方临时覆盖 top_k(rerank 召回阶段)
        effective_top_k = top_k if (top_k is not None and top_k > 0) else self.top_k

        # 1. query 向量化
        qv = self.embedding.encode_query(query)

        # 2. TopK 检索
        hits = self.vectorstore.search(qv, effective_top_k)
        if not hits:
            return []

        # 3. 阈值过滤 + 关联 chunk_id
        results = []
        for vector_id, score in hits:
            if score < self.score_threshold:
                continue
            chunk_id = self.vectorstore.get_chunk_id(vector_id)
            if chunk_id is None:
                continue
            results.append(RetrievalResult(
                vector_id=vector_id,
                chunk_id=chunk_id,
                score=round(score, 4),
            ))

        logger.info('[Knowledge:retriever] 检索: query_len=%s top_k=%s hits=%s 命中=%s',
                    len(query), effective_top_k, len(hits), len(results))
        return results
