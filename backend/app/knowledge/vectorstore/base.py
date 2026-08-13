"""
VectorStore 抽象基类(Sprint 4 - v0.6.0)

职责:
- 定义向量库统一契约:add / search / delete / save / load / size
- 业务代码禁止直接操作 FAISS(任务书约束),必须经本抽象

解耦(DI):
- VectorStore 通过构造函数接收 Embedding 实例,不 import 具体 Embedding 类
- Retriever 通过构造函数接收 VectorStore 实例,不 import 具体 VectorStore 类
- VectorStore 不依赖 Retriever / Service / DB

返回契约:
- add():返回分配的 vector_id 列表(供 service 回写 knowledge_chunks.vector_id)
- search():返回 [(vector_id, score)] 列表,score 为相似度(归一化余弦,0~1)
- delete():按 vector_id 删除
"""
from abc import ABC, abstractmethod
from typing import List, Tuple
import numpy as np


class BaseVectorStore(ABC):
    """向量库抽象基类"""

    @property
    @abstractmethod
    def size(self) -> int:
        """当前向量数"""
        raise NotImplementedError

    @abstractmethod
    def add(self, vectors: np.ndarray, chunk_ids: List[int],
            document_ids: List[int]) -> List[int]:
        """
        批量写入向量
        :param vectors: np.ndarray, shape=(n, dim),已归一化
        :param chunk_ids: 对应的 knowledge_chunks.id 列表(供溯源)
        :param document_ids: 对应的 knowledge_documents.id 列表
        :return: 分配的 vector_id 列表(供回写 knowledge_chunks.vector_id)
        """
        raise NotImplementedError

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Tuple[int, float]]:
        """
        检索 TopK
        :param query_vector: np.ndarray, shape=(dim,),已归一化
        :param top_k: 返回数量
        :return: [(vector_id, score)] 列表,按 score 降序
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, vector_ids: List[int]) -> int:
        """
        按 vector_id 删除向量
        :param vector_ids: 要删除的 vector_id 列表
        :return: 实际删除数量
        """
        raise NotImplementedError

    @abstractmethod
    def save(self) -> None:
        """持久化到磁盘"""
        raise NotImplementedError

    @abstractmethod
    def load(self) -> bool:
        """
        从磁盘加载
        :return: True 加载成功;False 无文件
        """
        raise NotImplementedError
