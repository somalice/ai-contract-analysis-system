"""
混合检索器 HybridRetriever(Sprint 8.8 Phase 3 - RAG 质量提升)

职责:
- 在保留 DenseRetriever(FAISS 稠密检索)的基础上,融合 BM25(稀疏关键词)检索,
  提升中文合同领域"专有名词/条款名称精确命中"的召回与精度
- 解决 Dense 检索"语义相近但非精确"的误召回问题(如『提存制度』『背靠背』等
  领域术语,BM25 词面命中可显著提升)

设计:
- 复用 DenseRetriever 的向量检索(vectorstore + embedding DI 注入),不重写稠密部分
- BM25 索引:基于 jieba 精确分词(缺失时降级字符 2-gram),零额外依赖
- 融合策略(Sprint 8.8 Phase 3 定稿): RRF(Reciprocal Rank Fusion)秩融合
    fused(chunk) = dense_weight * 1/(K + dense_rank) + bm25_weight * 1/(K + bm25_rank)
    - K=60(RRF 常数), rank 从 1 起
    - 秩融合不受两侧分数尺度差异影响,BM25 精确命中可稳定进入候选池
      (加权分数融合实测被 0.35 阈值阻断,BM25 单独命中无法越过阈值,见 Phase 3 实验)
- 阈值过滤: score = fused / max_fused 归一化到 [0,1] 后与 score_threshold 比较,
  保持与 DenseRetriever 一致的过滤语义(相对 Top 命中的比例)
- 候选池: 两侧各召回 max(top_k*3, 30),为下游 Reranker 提供足够多样性

兼容性:
- 实现 BaseRetriever 契约,retrieve(query) → list[RetrievalResult]
- RetrievalResult 与 DenseRetriever 完全一致(vector_id / chunk_id / score)
- Reranker(rerank_results)直接接收本类返回结果,天然兼容(不修改 reranker.py)
- 不影响生产链路:仅由评估实验(experiment.hybrid_*)或显式构造使用

约束:
- 不修改 DenseRetriever / vectorstore / embedding / reranker 任何代码
- corpus 通过 build_bm25 注入(chunk_id, vector_id, text),检索器不直接访问 DB
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional, Sequence, Tuple

from app.extensions.logger import logger
from app.knowledge.vectorstore.base import BaseVectorStore
from app.knowledge.embedding.base import BaseEmbedding
from .base import BaseRetriever, RetrievalResult

_CJK_PUNCT = set('，。、；：？！“”‘’（）《》【】…—·,.!?;:"\'()[]<>《》\s\t\n\r')


def _tokenize(text: str) -> List[str]:
    """分词: 优先 jieba 精确模式;jieba 不可用时降级字符 2-gram。

    返回词列表(保留重复,供 BM25 词频统计)。
    """
    if not text or not text.strip():
        return []
    try:
        import jieba
        return [t for t in jieba.cut(text, cut_all=False) if t and t.strip()]
    except Exception:
        cleaned = ''.join(' ' if c in _CJK_PUNCT else c for c in text)
        tokens = []
        for seg in re.split(r'\s+', cleaned):
            if not seg:
                continue
            if re.match(r'^[A-Za-z0-9_]+$', seg):
                tokens.append(seg.lower())
            else:
                # 中文 2-gram(兼容未登录词)
                for i in range(max(0, len(seg) - 1)):
                    bi = seg[i:i + 2]
                    if not any(c.isspace() for c in bi):
                        tokens.append(bi)
                if len(seg) == 1:
                    tokens.append(seg)
        return tokens


class BM25Index:
    """BM25 稀疏索引(Okapi BM25, k1=1.5, b=0.75)。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: List[Tuple[int, int, List[str]]] = []   # (chunk_id, vector_id, tokens)
        self._doc_len: List[int] = []
        self._avgdl: float = 0.0
        self._df: Counter = Counter()   # token -> 出现文档数
        self._n: int = 0
        self._built = False

    @property
    def built(self) -> bool:
        return self._built

    def build(self, corpus: Sequence[Tuple[int, int, str]]):
        """构建索引。

        :param corpus: [(chunk_id, vector_id, text), ...]
        """
        self._docs = []
        self._doc_len = []
        self._df = Counter()
        self._n = len(corpus)
        total_len = 0
        for chunk_id, vector_id, text in corpus:
            tokens = _tokenize(text or '')
            self._docs.append((chunk_id, vector_id, tokens))
            self._doc_len.append(len(tokens))
            total_len += len(tokens)
            for tok in set(tokens):
                self._df[tok] += 1
        self._avgdl = total_len / self._n if self._n else 0.0
        self._built = True
        logger.info('[Knowledge:hybrid] BM25 索引构建完成: docs=%s avgdl=%.1f',
                    self._n, self._avgdl)

    def _idf(self, df: int) -> float:
        """IDF(平滑,避免除零)。"""
        if self._n == 0:
            return 0.0
        return float(__import__('math').log(1 + (self._n - df + 0.5) / (df + 0.5)))

    def score(self, query_tokens: Sequence[str], doc_idx: int) -> float:
        """计算单篇文档 BM25 分数。"""
        _, _, tokens = self._docs[doc_idx]
        dl = self._doc_len[doc_idx]
        if dl == 0:
            return 0.0
        tf_counter = Counter(tokens)
        score = 0.0
        for term in set(query_tokens):
            tf = tf_counter.get(term, 0)
            if tf == 0:
                continue
            idf = self._idf(self._df.get(term, 0))
            denom = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
            score += idf * (tf * (self.k1 + 1)) / denom
        return score

    def search(self, query: str, top_k: Optional[int] = None) -> List[Tuple[int, int, float]]:
        """检索: 返回 [(chunk_id, vector_id, bm25_score)] 按分数降序。

        top_k=None 时返回全部分数 > 0 的结果(供融合阶段使用)。
        """
        if not self._built or self._n == 0:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scored = []
        for i in range(self._n):
            s = self.score(q_tokens, i)
            if s > 0:
                chunk_id, vector_id, _ = self._docs[i]
                scored.append((chunk_id, vector_id, s))
        scored.sort(key=lambda x: x[2], reverse=True)
        if top_k and top_k > 0:
            scored = scored[:top_k]
        return scored


class HybridRetriever(BaseRetriever):
    """Dense + BM25 混合检索器(RRF 秩融合)。"""

    def __init__(self, vectorstore: BaseVectorStore, embedding: BaseEmbedding,
                 top_k: int = 10, score_threshold: float = 0.35,
                 dense_weight: float = 0.5, bm25_weight: float = 0.5,
                 rrf_k: float = 60.0, bm25_k1: float = 1.5, bm25_b: float = 0.75):
        if top_k <= 0:
            raise ValueError('top_k 必须大于 0')
        if not (0.0 <= score_threshold <= 1.0):
            raise ValueError('score_threshold 必须在 [0, 1]')
        self.vectorstore = vectorstore
        self.embedding = embedding
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self.rrf_k = rrf_k
        self.bm25 = BM25Index(k1=bm25_k1, b=bm25_b)
        # 懒加载 dense(保持 DenseRetriever 原实现,不复制逻辑)
        from .dense_retriever import DenseRetriever
        self._dense = DenseRetriever(
            vectorstore=vectorstore, embedding=embedding,
            top_k=top_k, score_threshold=0.0,  # 阈值由 hybrid 融合后统一过滤
        )

    # ---------- 构建 / 刷新 ----------
    def build_bm25(self, corpus: Sequence[Tuple[int, int, str]]):
        """注入 BM25 语料(corpus: [(chunk_id, vector_id, text)])。"""
        self.bm25.build(corpus)

    def clear_bm25(self):
        self.bm25 = BM25Index()

    # ---------- 检索 ----------
    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[RetrievalResult]:
        """
        检索: Dense(FAISS) + BM25 → RRF 秩融合 → 归一化阈值过滤 → 排序

        :param query: 查询文本
        :param top_k: 可选 TopK 覆盖(None 用 self.top_k)
        :return: list[RetrievalResult],按融合分数降序
        """
        if not query or not query.strip():
            return []
        if self.vectorstore.size == 0:
            logger.info('[Knowledge:hybrid] 向量库为空,跳过检索')
            return []

        effective_top_k = top_k if (top_k is not None and top_k > 0) else self.top_k
        # 候选池: 两侧各召回 max(top_k*3, 30),为下游 Reranker 提供多样性
        n_cand = max(effective_top_k * 3, 30)

        # 1. Dense 召回(同 chunk 多向量取最高分)
        qv = self.embedding.encode_query(query)
        dense_hits = self.vectorstore.search(qv, n_cand)
        dense_map: Dict[int, Tuple[int, float]] = {}
        for vector_id, score in dense_hits:
            chunk_id = self.vectorstore.get_chunk_id(vector_id)
            if chunk_id is None:
                continue
            if chunk_id not in dense_map or score > dense_map[chunk_id][1]:
                dense_map[chunk_id] = (vector_id, float(score))
        dense_ranked = sorted(dense_map.items(), key=lambda kv: kv[1][1], reverse=True)

        # 2. BM25 召回
        bm25_hits = self.bm25.search(query)   # [(chunk_id, vector_id, score)]
        bm25_map: Dict[int, Tuple[int, float]] = {
            cid: (vid, float(s)) for cid, vid, s in bm25_hits}
        bm25_ranked = sorted(bm25_map.items(), key=lambda kv: kv[1][1], reverse=True)

        # 3. RRF 秩融合
        k = self.rrf_k
        fused: Dict[int, Tuple[int, float]] = {}   # chunk_id -> (vector_id, rrf)
        for i, (cid, (vid, _)) in enumerate(dense_ranked, 1):
            entry = fused.setdefault(cid, [vid, 0.0])
            entry[1] += self.dense_weight / (k + i)
        for i, (cid, (vid, _)) in enumerate(bm25_ranked, 1):
            entry = fused.setdefault(cid, [vid, 0.0])
            entry[1] += self.bm25_weight / (k + i)
        if not fused:
            return []

        # 4. 归一化阈值过滤(score = rrf / max_rrf,保持 DenseRetriever 过滤语义)
        max_rrf = max(v[1] for v in fused.values()) or 1.0
        results = []
        for cid, (vid, rrf) in fused.items():
            norm = rrf / max_rrf
            if norm < self.score_threshold:
                continue
            results.append(RetrievalResult(
                vector_id=vid,
                chunk_id=cid,
                score=round(norm, 4),
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:effective_top_k]
        logger.info('[Knowledge:hybrid] 检索: query_len=%s top_k=%s 融合命中=%s',
                    len(query), effective_top_k, len(results))
        return results
