"""
Embedding 抽象基类(Sprint 4 - v0.6.0)

职责:
- 定义文本向量化统一契约:encode(批量) / encode_query(单条) / dimension

解耦:
- Embedding 是最底层组件,不依赖 vectorstore / retriever
- VectorStore / Retriever 通过构造函数接收 Embedding 实例(依赖注入)
- 禁止调用 OpenAI Embedding(任务书约束)
"""
from abc import ABC, abstractmethod
import numpy as np


class BaseEmbedding(ABC):
    """文本向量化抽象基类"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        raise NotImplementedError

    @abstractmethod
    def encode(self, texts: list) -> np.ndarray:
        """
        批量编码文本(用于 chunk 向量化)
        :param texts: 文本列表
        :return: np.ndarray, shape=(len(texts), dimension),已归一化
        """
        raise NotImplementedError

    @abstractmethod
    def encode_query(self, text: str) -> np.ndarray:
        """
        编码单条查询(用于检索 query 向量化)
        :param text: 查询文本
        :return: np.ndarray, shape=(dimension,),已归一化
        """
        raise NotImplementedError
