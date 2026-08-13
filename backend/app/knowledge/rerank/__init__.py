"""
Rerank 包(Sprint 8.6 - v1.0.0 RAG 质量优化)

导出:
- get_reranker: 按 config 返回 reranker 实例(CrossEncoder / RuleBased / None)
- rerank_results: 对检索结果重排的高层入口(供 rag_service / run_rag_eval 复用)
"""
from .reranker import (
    CrossEncoderReranker,
    RuleBasedReranker,
    get_reranker,
    rerank_results,
)

__all__ = [
    'CrossEncoderReranker',
    'RuleBasedReranker',
    'get_reranker',
    'rerank_results',
]
