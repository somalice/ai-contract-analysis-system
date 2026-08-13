"""
Embedding 包(Sprint 4 - v0.6.0)

导出:
- BaseEmbedding:抽象基类
- SentenceTransformerEmbedding:sentence-transformers 实现(BAAI/bge-small-zh-v1.5)
"""
from .base import BaseEmbedding
from .sentence_transformer_embedding import SentenceTransformerEmbedding

__all__ = ['BaseEmbedding', 'SentenceTransformerEmbedding']
