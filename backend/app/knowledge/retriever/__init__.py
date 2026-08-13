"""
Retriever 包(Sprint 4 - v0.6.0 / Sprint 8.8 Hybrid Search)

导出:
- RetrievalResult:检索结果数据对象
- BaseRetriever:抽象基类
- DenseRetriever:稠密检索实现(TopK + Score Threshold)
- HybridRetriever:混合检索实现(Dense + BM25 融合, Sprint 8.8 Phase 3)
"""
from .base import RetrievalResult, BaseRetriever
from .dense_retriever import DenseRetriever
from .hybrid_retriever import HybridRetriever, BM25Index

__all__ = ['RetrievalResult', 'BaseRetriever', 'DenseRetriever',
           'HybridRetriever', 'BM25Index']
