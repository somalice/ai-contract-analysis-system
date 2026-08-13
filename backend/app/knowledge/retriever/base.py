"""
Retriever 抽象基类(Sprint 4 - v0.6.0)

职责:
- 定义检索统一契约:retrieve(query) → list[RetrievalResult]
- 预留 Hybrid Search 扩展(BaseRetriever + DenseRetriever,未来可加 HybridRetriever)

解耦(DI):
- Retriever 通过构造函数接收 VectorStore + Embedding 实例
- 不 import 具体实现类
- Retriever 不直接访问 DB(chunk 文本由 service 层按 vector_id 查 DB,
  保持 Retriever 与 DB 解耦)

返回契约:
- RetrievalResult: {vector_id, chunk_id, score}(score 为相似度)
- service 层据此查 knowledge_chunks 获取文本 + document 信息
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class RetrievalResult:
    """检索结果(不含文本,仅定位信息;文本由 service 层查 DB)"""
    vector_id: int
    chunk_id: int
    score: float


class BaseRetriever(ABC):
    """检索器抽象基类"""

    @abstractmethod
    def retrieve(self, query: str) -> List[RetrievalResult]:
        """
        检索与 query 最相关的 chunks
        :param query: 用户查询文本
        :return: list[RetrievalResult],按 score 降序,已过滤低于阈值的结果
        """
        raise NotImplementedError
