"""
VectorStore 包(Sprint 4 - v0.6.0)

导出:
- BaseVectorStore:抽象基类
- FaissVectorStore:FAISS 实现(IndexFlatIP + IndexIDMap2,本地持久化)
"""
from .base import BaseVectorStore
from .faiss_store import FaissVectorStore

__all__ = ['BaseVectorStore', 'FaissVectorStore']
