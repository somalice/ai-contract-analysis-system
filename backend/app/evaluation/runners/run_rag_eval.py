"""
RAG 评估运行器(Sprint 8.5)

执行:
    测试数据集(contract_qa_dataset.json)
        ↓
    复用现有 Retriever 组件 (vector_store_registry.retriever)
        ↓
    对每个问题: 检索 TopK → 取 chunk_text 列表(作为 context_chunks)
        ↓
    调用 rag_metrics.evaluate_single_sample (无需实际 LLM 调用,先做规则版评估)
        ↓
    聚合并返回结果

注意:
- Retriever / VectorStore / Embedding 均复用现有组件, 不重建链路
- 若实际需要 LLM 生成真实 answer 再评估, 可设置 use_llm_answer=True
  (需要 DeepSeek API 配置且消耗 Token)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import numpy as np


def _text_md5(text: str) -> str:
    """稳定文本哈希(评估缓存 key 用;规避 Python 内置 hash 的进程随机化)。"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


# 并行 worker 共享 timings 时的线程安全锁(Sprint 8.7)
_TIMINGS_LOCK = threading.Lock()


def _add_timing(timings: Dict[str, float], key: str, seconds: float):
    """线程安全累加阶段耗时(并行 worker 共享 timings dict)。"""
    if timings is None:
        return
    with _TIMINGS_LOCK:
        timings[key] = timings.get(key, 0.0) + seconds


# ============================================================
# Sprint 8.8 Phase 3: Hybrid Search 实验支持
# ============================================================
# HybridRetriever(保留 DenseRetriever 契约 + BM25 稀疏召回)仅在评估实验链路启用,
# 生产 RAG(rag_service.query_rag)仍使用 vector_store_registry.retriever(Dense)。
# BM25 语料(全量 active chunk)仅构建一次,后续检索线程共享(只读)。
_HYBRID_CACHE: Dict[tuple, Any] = {}
_HYBRID_LOCK = threading.Lock()


def _kb_epoch(db_session, KnowledgeChunk, KnowledgeDocument) -> str:
    """轻量知识库指纹(用于 HybridRetriever 缓存失效)。
    - 数量 + id 和: 覆盖 chunk 增删/重建(自增 id 变化)
    - 最新更新时间: 覆盖同 id 文本修改场景
    """
    try:
        from sqlalchemy import func as sa_func
        _join = (db_session.query(KnowledgeChunk.id)
                 .join(KnowledgeDocument,
                       KnowledgeChunk.document_id == KnowledgeDocument.id)
                 .filter(KnowledgeDocument.status == 'active'))
        cnt = _join.count()
        ids_sum = (
            db_session.query(sa_func.sum(KnowledgeChunk.id))
            .join(KnowledgeDocument,
                  KnowledgeChunk.document_id == KnowledgeDocument.id)
            .filter(KnowledgeDocument.status == 'active')
            .scalar()
        )
        max_upd = (
            db_session.query(sa_func.max(KnowledgeDocument.updated_time))
            .filter(KnowledgeDocument.status == 'active')
            .scalar()
        )
        upd_str = max_upd.strftime('%Y%m%d%H%M%S') if max_upd else 'none'
        return f'{cnt}:{ids_sum}:{upd_str}'
    except Exception:
        return 'unknown'


def _get_hybrid_retriever(exp: Dict[str, Any], db_session, KnowledgeChunk):
    """构造 / 复用 HybridRetriever(带 BM25 语料),供评估实验使用。

    :param exp: experiment dict,支持:
        retriever_top_k(int, 默认10) / retriever_threshold(float, 默认0.35)
        hybrid_dense_weight(float, 默认0.5) / hybrid_bm25_weight(float, 默认0.5)
    :param db_session: SQLAlchemy scoped_session 代理(线程安全分发)
    :param KnowledgeChunk: chunk 模型(避免函数内 import 循环)
    :return: HybridRetriever 实例(线程共享,只读检索)
    """
    from app.knowledge.services.vector_store_registry import vector_store_registry
    from app.knowledge.retriever import HybridRetriever
    from app.models.knowledge_document import KnowledgeDocument

    top_k = int(exp.get('retriever_top_k') or 10)
    threshold = float(exp.get('retriever_threshold') or 0.35)
    dense_w = float(exp.get('hybrid_dense_weight') or 0.5)
    bm25_w = float(exp.get('hybrid_bm25_weight') or 0.5)
    key = (top_k, threshold, dense_w, bm25_w,
           _kb_epoch(db_session, KnowledgeChunk, KnowledgeDocument))

    with _HYBRID_LOCK:
        hb = _HYBRID_CACHE.get(key)
        if hb is not None:
            return hb
        rows = (
            db_session.query(KnowledgeChunk.id, KnowledgeChunk.vector_id,
                             KnowledgeChunk.text)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .filter(KnowledgeDocument.status == 'active')
            .all()
        )
        corpus = [(cid, vid if vid is not None else -1, text or '')
                  for cid, vid, text in rows]
        hb = HybridRetriever(
            vectorstore=vector_store_registry.vectorstore,
            embedding=vector_store_registry.embedding,
            top_k=top_k,
            score_threshold=threshold,
            dense_weight=dense_w,
            bm25_weight=bm25_w,
        )
        hb.build_bm25(corpus)
        _HYBRID_CACHE[key] = hb
        return hb


def clear_hybrid_cache():
    """清空 HybridRetriever 缓存(实验运行器重建知识库后调用)。"""
    with _HYBRID_LOCK:
        _HYBRID_CACHE.clear()


def load_dataset(dataset_path: str, sample_size: Optional[int] = None) -> List[Dict[str, str]]:
    """加载测试数据集(可选采样)。"""
    with open(dataset_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if sample_size and sample_size > 0 and len(data) > sample_size:
        random.seed(42)
        data = random.sample(data, sample_size)
    return data


def _retrieve_chunks(retriever, db_session, KnowledgeChunk, query: str,
                     use_rerank: Optional[bool] = None,
                     timings: Optional[Dict[str, float]] = None,
                     experiment: Optional[Dict[str, Any]] = None):
    """
    通过 retriever 检索 → 返回 3 元组 (chunk_text 列表, RetrievalResult 列表, hit_doc_ids 集合)。

    hit_doc_ids: 本次检索命中的知识文档 ID 集合,用于统计知识库命中率。

    Sprint 8.6: 若 RERANK_ENABLED,在检索后注入 rerank 重排(与生产 rag_service 同路径),
    确保评估能观测到 rerank 优化效果。

    Sprint 8.7: 评估性能优化
    - use_rerank: None=跟随生产 config RERANK_ENABLED; False=关闭 rerank(仅评估 quick 模式,
      不影响生产 RAG 链路); True=强制开启
    - timings: 可选耗时统计 dict,累加 dense(检索+query embedding) / rerank 阶段时长,
      供 evaluation_summary.performance 定位瓶颈

    Sprint 8.8: 实验覆盖(仅评估链路,生产 RAG 链路不受影响)
    - experiment: 可选 dict,支持
        force_rerank(bool): 强制开启 rerank(quick 模式实验)
        retriever_mode(str): 'dense'(默认) | 'hybrid'(Phase 3: Dense+BM25 融合)
        retriever_top_k(int): 覆盖召回 TopK
        retriever_threshold(float): 覆盖相似度阈值(dense 运行期覆盖 / hybrid 烘焙进构造)
        hybrid_dense_weight / hybrid_bm25_weight(float): hybrid 融合权重(默认 0.5/0.5)
        rerank_recall_k / rerank_final_top_k(int): 覆盖 rerank 召回/最终条数
    """
    from app.knowledge.services.vector_store_registry import vector_store_registry
    exp = experiment or {}
    # Sprint 8.8 Phase 3: Hybrid 检索实验(experiment.retriever_mode='hybrid')
    # 保留 DenseRetriever 为默认;hybrid 仅在评估实验链路启用,生产 RAG 不受影响
    hybrid_retriever = None
    if exp.get('retriever_mode') == 'hybrid':
        hybrid_retriever = _get_hybrid_retriever(exp, db_session, KnowledgeChunk)
        real_retriever = hybrid_retriever
    else:
        real_retriever = retriever or vector_store_registry.retriever
    if real_retriever is None:
        return [], [], set()
    # Sprint 8.8: 实验覆盖 retriever top_k / threshold(仅评估;生产链路保持不变)
    ret_top_k = exp.get('retriever_top_k')
    ret_thr = exp.get('retriever_threshold')
    _saved_thr = None
    if ret_thr is not None and hybrid_retriever is None:
        # 仅 Dense 模式支持运行期阈值覆盖;Hybrid 阈值已烘焙进构造参数(避免共享实例竞态)
        _saved_thr = getattr(real_retriever, 'score_threshold', None)
        try:
            real_retriever.score_threshold = float(ret_thr)
        except Exception:
            _saved_thr = None
    _t0 = time.time()
    try:
        retrieval_results = real_retriever.retrieve(query, top_k=ret_top_k)
    finally:
        # 实验结束后恢复 retriever 原阈值,避免影响同进程其他调用
        if _saved_thr is not None:
            try:
                real_retriever.score_threshold = _saved_thr
            except Exception:
                pass
    _add_timing(timings, 'dense', time.time() - _t0)
    if not retrieval_results:
        return [], [], set()

    # Sprint 8.6: rerank 注入(与 rag_service.query_rag 同逻辑)
    # Sprint 8.7: use_rerank 覆盖(评估 quick 模式关闭 rerank,生产链路不受影响)
    try:
        from flask import current_app as _ca
        rerank_enabled = bool(_ca.config.get('RERANK_ENABLED'))
        if use_rerank is not None:
            rerank_enabled = use_rerank
        if rerank_enabled:
            # Sprint 8.8: 实验覆盖 recall_k / final_top_k(仅评估;生产读 config)
            recall_k = exp.get('rerank_recall_k') or _ca.config.get('RERANK_RECALL_K', 15)
            if len(retrieval_results) < recall_k:
                _t1 = time.time()
                retrieval_results = real_retriever.retrieve(query, top_k=recall_k)
                _add_timing(timings, 'dense', time.time() - _t1)
            from app.knowledge.rerank import rerank_results
            _t2 = time.time()
            final_k = exp.get('rerank_final_top_k') or _ca.config.get('RERANK_FINAL_TOP_K', 5)
            retrieval_results = rerank_results(
                query, retrieval_results,
                final_k=final_k,
                db_session=db_session,
                KnowledgeChunk=KnowledgeChunk,
            )
            _add_timing(timings, 'rerank', time.time() - _t2)
    except Exception as _re:
        # rerank 失败不阻断评估,使用原检索结果
        pass

    # 关联 DB chunk 文本
    chunk_ids = [r.chunk_id for r in retrieval_results if r.chunk_id]
    if not chunk_ids:
        return [], [], set()
    try:
        chunks = (
            db_session.query(KnowledgeChunk)
            .filter(KnowledgeChunk.id.in_(chunk_ids))
            .all()
        )
    except Exception:
        return [], [], set()
    # 按检索顺序排列
    # 注:KnowledgeChunk 模型的文本字段名为 `text`(非 chunk_text)
    id_to_text = {c.id: c.text or '' for c in chunks}
    id_to_doc = {c.id: c.document_id for c in chunks}
    ordered = []
    hit_doc_ids = set()
    for cid in chunk_ids:
        txt = id_to_text.get(cid)
        if txt:
            ordered.append(txt)
            doc_id = id_to_doc.get(cid)
            if doc_id:
                hit_doc_ids.add(doc_id)
    return ordered, retrieval_results, hit_doc_ids


def _extract_relevant_sentences(question: str, context_chunks: List[str],
                                max_chars: int = 400,
                                sim_fn: Optional[Callable[[str, str], float]] = None) -> str:
    """
    context_extract 模式:从检索 context 中抽取与问题最相关的句子拼接为 answer。

    策略:
    1. 把 context_chunks 按句号/分号/换行切句
    2. Sprint 8.6: 若提供 sim_fn(embedding 语义相似度),用语义相似度选句;
       否则回退 bigram Jaccard + 关键词覆盖率(原行为)
    3. 按 score 降序取前 N 句,直到 max_chars,保持原文顺序拼接
    4. 无句或全 0 分 → 返回前 2 个 chunk 的前 200 字

    该模式让 answer 直接来自 context → Faithfulness 反映检索质量上限 +
    生成器忠实度(合法评估模式,避免 ground_truth 措辞差异致指标失真)。
    """
    if not context_chunks:
        return ''
    import re as _re

    # 切句(保留中文句号/分号/换行)
    sentences = []
    for chunk in context_chunks:
        for s in _re.split(r'(?<=[。；;\n])', chunk):
            s = s.strip()
            if s and len(s) >= 2:
                sentences.append(s)
    if not sentences:
        # 退化为前 2 chunk 前 200 字
        return '\n'.join(c[:200] for c in context_chunks[:2])

    # question tokens(2-gram)
    q_tokens = set()
    cleaned_q = ''.join(' ' if c in '，。、；：？！,.!?;:' else c for c in question)
    for seg in _re.split(r'\s+', cleaned_q):
        if _re.match(r'^[A-Za-z0-9_]+$', seg):
            q_tokens.add(seg.lower())
        else:
            for i in range(max(0, len(seg) - 1)):
                bi = seg[i:i + 2]
                if not any(c.isspace() for c in bi):
                    q_tokens.add(bi)

    def _score(sent: str) -> float:
        # Sprint 8.6: 语义选句模式(embedding 余弦相似度,与指标 sim_fn 对齐)
        if sim_fn is not None:
            return sim_fn(question, sent)
        s_tokens = set()
        cleaned_s = ''.join(' ' if c in '，。、；：？！,.!?;:' else c for c in sent)
        for seg in _re.split(r'\s+', cleaned_s):
            if _re.match(r'^[A-Za-z0-9_]+$', seg):
                s_tokens.add(seg.lower())
            else:
                for i in range(max(0, len(seg) - 1)):
                    bi = seg[i:i + 2]
                    if not any(c.isspace() for c in bi):
                        s_tokens.add(bi)
        if not q_tokens or not s_tokens:
            return 0.0
        inter = len(q_tokens & s_tokens)
        union = len(q_tokens | s_tokens)
        return inter / union if union > 0 else 0.0

    # 打分 + 取 top(直到 max_chars)
    scored = [(i, s, _score(s)) for i, s in enumerate(sentences)]
    if sim_fn is not None:
        # 语义模式:按分数降序取最相关句子(保证 answer 与 question 语义最贴近),
        # 再按原文顺序拼接(保持可读性)
        scored.sort(key=lambda x: x[2], reverse=True)
        top = scored[:max(3, len(scored) // 4)]
        top.sort(key=lambda x: x[0])  # 恢复原文顺序
        relevant = [(i, s) for i, s, sc in top if sc > 0.05]
    else:
        # 规则模式:取 score > 0 的前 N 句,按原序拼接
        relevant = [(i, s) for i, s, sc in scored if sc > 0]
        relevant.sort(key=lambda x: x[0])  # 保持原文顺序
    result_parts = []
    total = 0
    for _, s in relevant:
        if total + len(s) > max_chars:
            break
        result_parts.append(s)
        total += len(s)
    if not result_parts:
        # 全 0 分 → 退化为前 2 chunk 前 200 字
        return '\n'.join(c[:200] for c in context_chunks[:2])
    return '。'.join(result_parts)


def _build_answer(mode: str, question: str, context_chunks: List[str],
                  ground_truth: str,
                  sim_fn: Optional[Callable[[str, str], float]] = None) -> str:
    """
    根据模式构造评估用 answer。

    :param mode: 'context_extract' | 'llm' | 'ground_truth'
        - context_extract(默认):从 context 抽相关句(answer⊆context,Faithfulness 高)
        - llm:返回空串(由调用方走 use_llm_answer 路径调 query_rag)
        - ground_truth:原行为(返回 ground_truth,模拟理想生成器)
    :param sim_fn: Sprint 8.6 语义相似度函数,供 context_extract 语义选句
    :return: answer 字符串
    """
    if mode == 'llm':
        return ''  # 调用方走 use_llm_answer 路径
    if mode == 'ground_truth':
        if ground_truth:
            return ground_truth
        if context_chunks:
            return '\n'.join(context_chunks[:2])
        return ''
    # context_extract(默认)
    return _extract_relevant_sentences(question, context_chunks, sim_fn=sim_fn)


def _build_synthetic_answer(question: str, context_chunks: List[str], ground_truth: str) -> str:
    """
    [已废弃,保留向后兼容] 无 LLM 时构造"合成 answer"。
    Sprint 8.6: 请使用 _build_answer(mode, ...)。
    """
    return _build_answer('ground_truth', question, context_chunks, ground_truth)


# ============================================================
# Sprint 8.6: 语义相似度函数(基于已加载的 Embedding 模型)
# ============================================================
def _make_sim_fn(embedding, embedding_cache=None, model_name: str = '',
                 timings: Optional[Dict[str, float]] = None):
    """
    基于 Embedding 模型构造语义相似度函数 sim_fn(text_a, text_b) -> float in [0, 1]。

    用途: 传递给 rag_metrics.evaluate_single_sample(sim_fn=...),
    使 4 项 RAG 指标使用 embedding 余弦相似度替代 Jaccard 表面 token 匹配。

    实现:
    - 复用 vector_store_registry.embedding(已加载的 bge-small-zh-v1.5)
    - encode 两个文本 → L2 归一化 → 内积 = 余弦相似度
    - 映射到 [0, 1]: max(0, cos)(负相似度视为不相关)
    - 内置 LRU 缓存避免重复 encode(question / ground_truth 在多指标中复用)

    Sprint 8.7 优化:
    - embedding_cache: 持久化 Embedding Cache(模型一致时跨运行命中,跳过推理)
    - _prefetch(texts): 批量编码未缓存文本(一次 model.encode,替代逐条 encode_query),
      评估前预取 question / ground_truth 向量,指标阶段近乎零推理开销
    - timings: 累计 embedding 推理耗时(供 performance 定位瓶颈)

    :param embedding: SentenceTransformerEmbedding 实例(或任何有 encode_query 方法的对象)
    :return: sim_fn 可调用对象; embedding=None 时返回 None(回退规则降级)
    """
    if embedding is None:
        return None

    _cache: Dict[str, np.ndarray] = {}
    _timings = timings if timings is not None else {}
    _timings_lock = threading.Lock()

    def _add_embedding_time(seconds: float):
        """线程安全累加 embedding 推理耗时(并行 worker 共享 sim_fn)。"""
        with _timings_lock:
            _timings['embedding'] = _timings.get('embedding', 0.0) + seconds

    def _encode(text: str) -> Optional[np.ndarray]:
        if not text or not text.strip():
            return None
        key = _text_md5(text)
        if key in _cache:
            return _cache[key]
        # Sprint 8.7: 持久化 embedding cache 命中 → 跳过推理
        if embedding_cache is not None and model_name:
            cached = embedding_cache.get(text, model_name)
            if cached is not None:
                vec = np.asarray(cached, dtype=np.float32).flatten()
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                _cache[key] = vec
                return vec
        _t = time.time()
        try:
            vec = embedding.encode_query(text)
            vec = np.asarray(vec, dtype=np.float32).flatten()
            # L2 归一化(内积 = 余弦相似度)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
        except Exception:
            return None
        _add_embedding_time(time.time() - _t)
        _cache[key] = vec
        if embedding_cache is not None and model_name:
            embedding_cache.put(text, vec, model_name)
        return vec

    def _prefetch(texts: List[str]):
        """
        批量编码未缓存文本(一次 model.encode,保持结果与 encode_query 一致)。
        评估前预取 question / ground_truth / context chunk,显著降低指标阶段推理次数。
        """
        if not texts or embedding is None:
            return
        miss = []
        for t in texts:
            if not t or not t.strip():
                continue
            key = _text_md5(t)
            if key in _cache:
                continue
            if embedding_cache is not None and model_name and embedding_cache.get(t, model_name) is not None:
                continue
            miss.append(t)
        if not miss:
            return
        _t = time.time()
        try:
            # Sprint 8.7: 显式 batch_size=16(与 encode_query 输出一致,已归一化)
            vecs = embedding.encode(miss, batch_size=16)
        except Exception:
            return
        _add_embedding_time(time.time() - _t)
        for t, v in zip(miss, vecs):
            v = np.asarray(v, dtype=np.float32).flatten()
            _cache[_text_md5(t)] = v
            if embedding_cache is not None and model_name:
                embedding_cache.put(t, v, model_name)

    def sim_fn(text_a: str, text_b: str) -> float:
        va = _encode(text_a)
        vb = _encode(text_b)
        if va is None or vb is None:
            return 0.0
        cos = float(np.dot(va, vb))
        # 映射到 [0, 1](负相似度视为不相关)
        return max(0.0, min(1.0, cos))

    sim_fn._prefetch = _prefetch  # type: ignore[attr-defined]
    return sim_fn


def run_rag_evaluation(
    app,
    db_session,
    dataset_path: str,
    sample_size: Optional[int] = None,
    use_llm_answer: bool = False,
    llm_user: Optional[Dict] = None,
    evaluation_mode: str = 'quick',
    progress_callback: Optional[Callable[[int, int], None]] = None,
    enable_cache: bool = True,
    parallel_workers: Optional[int] = None,
    experiment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    执行 RAG 评估。

    Sprint 8.6 收尾: 双模式 Answer 生成策略。
    - evaluation_mode='quick'(默认, 开发调参):
        answer = ground_truth(原行为), 不消耗 Token, 指标反映检索质量上限。
    - evaluation_mode='production'(发布验收):
        强制 use_llm_answer=True, 调用 DeepSeek 基于检索 context 生成 answer,
        真实评估 Faithfulness / Answer Relevancy(消耗 Token)。
    - 保留 ANSWER_MODE=context_extract 兼容: 当 quick/production 未显式指定
      且调用方未走 LLM 路径时, 仍按原配置回退。

    Sprint 8.6.1(异步任务): progress_callback 可选参数,每完成一道题回调
    (done: 已完成题数, total: 总题数),供异步任务实时上报进度。
    默认 None 时行为完全不变(向后兼容)。

    Sprint 8.7(性能优化):
    - enable_cache: 是否启用评估缓存(context cache + embedding cache)。
      数据集 / 知识库 / embedding 模型 / rerank 配置变化时自动失效,不影响指标可复现。
    - parallel_workers: 并行 worker 数(None=读 config EVALUATION_WORKERS,默认 8;1=串行)。
      每 worker 独立 app context,保证 db session 线程隔离;FAISS/rerank 只读,线程安全。
    - evaluation_mode='quick' 时关闭 rerank(仅评估层,不影响生产 RAG 链路)。
    - 返回新增 performance 字段(各阶段耗时 + cache 命中率),供 summary 落盘定位瓶颈。

    :return: dict(dataset, per_sample_scores, aggregate, duration_ms, evaluation_mode,
                  answer_generation, performance)
    """
    from app.models.knowledge_chunk import KnowledgeChunk
    from app.evaluation.metrics.rag_metrics import evaluate_single_sample, aggregate_scores

    # Sprint 8.7: 若传入的是 current_app(LocalProxy),先解析为真实应用对象。
    # 并行 worker 在线程中 push app context,LocalProxy 无法跨线程解析 current_app。
    if hasattr(app, '_get_current_object'):
        app = app._get_current_object()

    t0 = time.time()
    timings: Dict[str, float] = {}  # dense / rerank / metric 阶段累计耗时(embedding 由 sim_fn 内部统计)

    # ---------- 1. 加载数据 ----------
    samples = load_dataset(dataset_path, sample_size=sample_size)
    dataset_info = {
        'path': dataset_path,
        'count': len(samples),
        'category_count': {},
    }
    for s in samples:
        c = s.get('category', 'unknown')
        dataset_info['category_count'][c] = dataset_info['category_count'].get(c, 0) + 1

    # ---------- 2. 确保 retriever 已初始化 ----------
    from app.knowledge.services.vector_store_registry import vector_store_registry
    with app.app_context():
        if not getattr(vector_store_registry, '_initialized', False):
            vector_store_registry.load(app)

        # Sprint 8.7: 评估缓存(仅评估链路,不影响生产 RAG)
        ctx_cache = None
        emb_cache = None
        model_name = app.config.get('EMBEDDING_MODEL', 'BAAI/bge-small-zh-v1.5')
        if enable_cache:
            try:
                from app.evaluation.cache import EvaluationContextCache, EvaluationEmbeddingCache
                cache_dir = Path(app.root_path) / 'evaluation' / 'cache'
                ctx_cache = EvaluationContextCache(str(cache_dir))
                emb_cache = EvaluationEmbeddingCache(str(cache_dir))
            except Exception as e:
                app.logger.warning('[RAG Eval] 评估缓存初始化失败,本次运行禁用缓存: %s', e)
                ctx_cache = None
                emb_cache = None

        # Sprint 8.6: 构造语义相似度函数(基于已加载的 Embedding 模型)
        # 使 4 项 RAG 指标使用 embedding 余弦相似度替代 Jaccard 表面 token 匹配
        # embedding=None 时返回 None → 指标回退规则降级(完全向后兼容)
        sim_fn = _make_sim_fn(
            getattr(vector_store_registry, 'embedding', None),
            embedding_cache=emb_cache,
            model_name=model_name,
            timings=timings,
        )
        if sim_fn is not None:
            app.logger.info('[RAG Eval] Sprint 8.6 语义模式已启用: '
                            'RAG 指标使用 embedding 余弦相似度(替代 Jaccard)')

        # Sprint 8.7: 批量预取 question / ground_truth embedding(一次 model.encode,
        # 替代逐条 encode_query;持久化命中时零推理开销)
        if sim_fn is not None and hasattr(sim_fn, '_prefetch'):
            prefetch_texts: List[str] = []
            for s in samples:
                prefetch_texts.append(s.get('question', ''))
                prefetch_texts.append(s.get('ground_truth', ''))
            sim_fn._prefetch(prefetch_texts)
            if emb_cache is not None:
                emb_cache.flush()

        # Sprint 8.7: quick 模式关闭 rerank(仅评估层生效,不影响生产 RAG 链路)
        use_rerank: Optional[bool] = None
        if evaluation_mode == 'quick':
            use_rerank = False
        # Sprint 8.8: 实验覆盖(force_rerank=True 强制开启 rerank,仅评估实验)
        _exp = experiment or {}
        if _exp.get('force_rerank'):
            use_rerank = True
        # 并行场景下预热 reranker,避免 worker 并发首次加载竞态
        need_rerank = (use_rerank if use_rerank is not None
                       else bool(app.config.get('RERANK_ENABLED', False)))
        if need_rerank:
            try:
                from app.knowledge.rerank import get_reranker
                get_reranker()
            except Exception:
                pass

        per_sample = []
        skipped_no_context = 0
        all_hit_doc_ids = set()  # 累计所有命中过的知识文档 ID,用于统计知识库命中率
        # Sprint 8.6 收尾: 记录实际使用的 Answer 生成方式(quick=ground_truth / production=llm)
        actual_generation = 'ground_truth'
        if evaluation_mode == 'production':
            actual_generation = 'llm'

        # ---------- 3. 逐题处理(Sprint 8.7: 可并行;worker 内独立 app context) ----------
        def _process_one(idx: int, sample: Dict[str, str]) -> Dict[str, Any]:
            with app.app_context():
                question = sample.get('question', '')
                ground_truth = sample.get('ground_truth', '')
                category = sample.get('category', '')

                # (a) 检索(context cache 命中 → 跳过 embedding + FAISS + rerank)
                context_chunks: List[str] = []
                hit_doc_ids: set = set()
                if ctx_cache is not None:
                    _cached = ctx_cache.get(question, app, dataset_path, db_session,
                                            use_rerank=use_rerank)
                    if _cached is not None:
                        context_chunks = list(_cached.get('retrieved_chunks') or [])
                        hit_doc_ids = set(_cached.get('hit_doc_ids') or [])
                if not context_chunks and not hit_doc_ids:
                    # 缓存未命中(或空结果) → 真实检索(dense/rerank 计时由 _retrieve_chunks 内部统计)
                    try:
                        _chunks, _results, _hits = _retrieve_chunks(
                            None, db_session, KnowledgeChunk, question,
                            use_rerank=use_rerank, timings=timings,
                            experiment=experiment,
                        )
                        context_chunks, hit_doc_ids = _chunks, _hits
                        if ctx_cache is not None:
                            ctx_cache.put(
                                question,
                                context_chunks,
                                [r.chunk_id for r in _results if r.chunk_id],
                                [r.score for r in _results],
                                sorted(hit_doc_ids),
                                app, dataset_path, db_session,
                                use_rerank=use_rerank,
                            )
                    except Exception as e:
                        app.logger.warning('[RAG Eval] 检索失败 q#%s: %s', idx, e)
                        context_chunks = []

                # (b) 构造 answer (LLM / 规则合成)
                answer = ''
                llm_error = None
                answer_mode = 'context_extract'
                try:
                    from flask import current_app as _ca
                    answer_mode = _ca.config.get('ANSWER_MODE', 'context_extract')
                except Exception:
                    pass
                # Sprint 8.6 收尾: 双模式覆盖(quick=ground_truth 开发调参 / production=LLM 发布验收)
                # Sprint 8.7: 补 standard 分支(51 题完整评估,保留 rerank,answer=context_extract,
                # 不耗 Token),修复 8.6.1 潜伏的 use_llm_answer 未赋值 UnboundLocalError
                if evaluation_mode == 'quick':
                    answer_mode = 'ground_truth'
                    use_llm_answer = False
                elif evaluation_mode == 'production':
                    answer_mode = 'llm'
                    use_llm_answer = True
                else:
                    # standard / 其他模式: 规则级 context_extract,不调用 LLM
                    answer_mode = 'context_extract'
                    use_llm_answer = False
                if use_llm_answer or answer_mode == 'llm':
                    try:
                        from app.knowledge.services.rag_service import query_rag
                        user = llm_user or {'id': 1, 'username': 'eval_agent', 'role': 'admin'}
                        with app.app_context():
                            res = query_rag(question, user)
                            answer = res.get('answer') or ''
                            llm_error = res.get('llm_error')
                    except Exception as e:
                        app.logger.warning('[RAG Eval] LLM 生成失败 q#%s: %s', idx, e)
                        llm_error = str(e)
                if not answer:
                    # LLM 失败时回退 context_extract,保证 production 模式仍有可评估 answer
                    fallback_mode = 'context_extract' if answer_mode == 'llm' else answer_mode
                    answer = _build_answer(fallback_mode, question, context_chunks, ground_truth,
                                           sim_fn=sim_fn)

                # 注:Sprint 8.7 实测,worker 内并发 _prefetch 共享 _cache 会导致重复批量编码
                # 与 torch 线程竞争(embedding 耗时暴涨),故指标阶段不做 worker 级 prefetch,
                # 依赖外部 question/gt 预取 + sim_fn 内存/持久缓存即可。

                # (c) 打分(Sprint 8.6: 传入 sim_fn 使用语义相似度)
                _t_m = time.time()
                scores = evaluate_single_sample(
                    question=question,
                    answer=answer,
                    context_chunks=context_chunks,
                    ground_truth=ground_truth,
                    sim_fn=sim_fn,
                )
                _add_timing(timings, 'metric', time.time() - _t_m)

                # (d) Sprint 8.9: 知识覆盖判定(复用已计算的 context_chunks/sim_fn/检索结果,
                #     不重复 embedding / rerank / LLM; 判定仅用于诊断分类,不参与 4 项指标)
                coverage = {'level': 'unknown', 'confidence': 0.0, 'evidence': {}}
                hit_doc_titles: List[str] = []
                if hit_doc_ids:
                    try:
                        from app.models.knowledge_document import KnowledgeDocument
                        _docs = (
                            db_session.query(KnowledgeDocument)
                            .filter(KnowledgeDocument.id.in_(sorted(hit_doc_ids)))
                            .all()
                        )
                        hit_doc_titles = [d.title or '' for d in _docs if d.title]
                    except Exception:
                        hit_doc_titles = []
                try:
                    from app.evaluation.knowledge_coverage import judge_coverage
                    coverage = judge_coverage(
                        question=question,
                        ground_truth=ground_truth,
                        context_chunks=context_chunks,
                        hit_doc_titles=hit_doc_titles,
                        source_document=sample.get('source_document', ''),
                        sim_fn=sim_fn,
                        source_type=sample.get('source_type', ''),
                        kb_coverage=sample.get('knowledge_coverage', ''),
                    )
                except Exception as e:
                    app.logger.warning('[RAG Eval] 知识覆盖判定失败 q#%s: %s', idx, e)

                return {
                    'index': idx,
                    'category': category,
                    'question': question,
                    'context_count': len(context_chunks),
                    'scores': scores,
                    'has_context': len(context_chunks) > 0,
                    'used_llm': use_llm_answer,
                    'llm_error': llm_error,
                    'answer': answer,
                    'hit_doc_ids': sorted(hit_doc_ids),
                    'hit_doc_titles': hit_doc_titles,
                    'knowledge_coverage': coverage.get('level', 'unknown'),
                    'coverage_confidence': coverage.get('confidence', 0.0),
                    'coverage_evidence': coverage.get('evidence', {}),
                    'source_type': sample.get('source_type', ''),
                    'knowledge_category': sample.get('knowledge_category', ''),
                    'source_document': sample.get('source_document', ''),
                    # Sprint 8.9: 检索 context 预览(诊断报告引用,不参与指标)
                    'context_preview': '\n'.join(context_chunks)[:300],
                }

        # 并行 / 串行执行
        workers = parallel_workers
        if workers is None:
            workers = int(app.config.get('EVALUATION_WORKERS', 8) or 1)
        if workers and workers > 1 and len(samples) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='rageval') as _ex:
                _futures = [_ex.submit(_process_one, idx, s) for idx, s in enumerate(samples)]
                for _done, _f in enumerate(_futures):
                    per_sample.append(_f.result())
                    # Sprint 8.6.1: 实时进度回调
                    if progress_callback is not None:
                        try:
                            progress_callback(_done + 1, len(samples))
                        except Exception as _pe:
                            import logging
                            logging.getLogger('app').warning(
                                '[RAG Eval] 进度回调失败: %s', _pe)
        else:
            for idx, s in enumerate(samples):
                per_sample.append(_process_one(idx, s))
                # Sprint 8.6.1: 实时进度回调
                if progress_callback is not None:
                    try:
                        progress_callback(idx + 1, len(samples))
                    except Exception as _pe:
                        import logging
                        logging.getLogger('app').warning(
                            '[RAG Eval] 进度回调失败 q#%s: %s', idx, _pe)

        # 汇总命中/跳过/生成方式
        for s in per_sample:
            if s['has_context']:
                all_hit_doc_ids.update(s.get('hit_doc_ids') or [])
            else:
                skipped_no_context += 1
        if evaluation_mode == 'production' and any(
                s.get('used_llm') and s.get('answer') for s in per_sample):
            actual_generation = 'llm'

        # Sprint 8.7: 落盘 embedding cache(内存新增向量写盘)
        if emb_cache is not None:
            try:
                emb_cache.flush()
            except Exception:
                pass

        # ---------- 4. 聚合 ----------
        only_with_context_scores = [
            s['scores'] for s in per_sample if s['has_context']
        ]
        all_scores = [s['scores'] for s in per_sample]
        aggregate_all = aggregate_scores(all_scores)
        aggregate_with_ctx = aggregate_scores(only_with_context_scores)

        # 按类别聚合
        per_category = {}
        for cat in set(s['category'] for s in per_sample):
            cat_scores = [s['scores'] for s in per_sample if s['category'] == cat]
            per_category[cat] = aggregate_scores(cat_scores)

        # Sprint 8.9: 知识覆盖统计 + 按覆盖度子集拆分指标
        # 核心结论判断: 若 Covered 子集指标达标而 All 不达标 → RAG 核心能力正常,
        # 全量指标受知识库覆盖不足限制(而非 Retriever/Chunk/Reranker 问题)。
        from app.evaluation.knowledge_coverage import aggregate_coverage
        knowledge_coverage_stats = aggregate_coverage(per_sample)
        _cov_meta = {'covered': 'covered', 'partial': 'partial', 'not_covered': 'not_covered'}
        aggregate_by_coverage = {}
        for _key, _level in _cov_meta.items():
            _subset = [s['scores'] for s in per_sample
                       if (s.get('knowledge_coverage') or 'unknown') == _level]
            aggregate_by_coverage[_key] = aggregate_scores(_subset)

    dur_ms = int((time.time() - t0) * 1000)
    # Sprint 8.7: 性能统计(供 evaluation_summary.json 定位瓶颈)
    cache_stats = ctx_cache.stats if ctx_cache is not None else {
        'hit_count': 0, 'total_count': 0, 'hit_rate': 0.0, 'cached_questions': 0,
    }
    performance = {
        'total_seconds': round(dur_ms / 1000, 2),
        'embedding_seconds': round(timings.get('embedding', 0.0), 2),
        'retrieval_seconds': round(timings.get('dense', 0.0), 2),
        'rerank_seconds': round(timings.get('rerank', 0.0), 2),
        'metric_seconds': round(timings.get('metric', 0.0), 2),
        'cache_hit_rate': cache_stats.get('hit_rate', 0.0),
        'cache_hit_count': cache_stats.get('hit_count', 0),
        'cache_total_count': cache_stats.get('total_count', 0),
        'cache_enabled': enable_cache and ctx_cache is not None,
        'parallel_workers': workers if (workers and workers > 1) else 1,
        'use_rerank': not (use_rerank is False),
    }
    return {
        'evaluated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'dataset': dataset_info,
        'sample_count': len(samples),
        'samples_with_context': len(samples) - skipped_no_context,
        'samples_without_context': skipped_no_context,
        'hit_document_ids': sorted(all_hit_doc_ids),
        'hit_document_count': len(all_hit_doc_ids),
        'aggregate_all': aggregate_all,
        'aggregate_with_context': aggregate_with_ctx,
        'per_category': per_category,
        'per_sample': per_sample,
        'knowledge_coverage': knowledge_coverage_stats,
        'aggregate_by_coverage': aggregate_by_coverage,
        'duration_ms': dur_ms,
        # Sprint 8.6 收尾: 评估模式 + Answer 生成方式(供 summary 落盘/报告注明)
        'evaluation_mode': evaluation_mode,
        'answer_generation': actual_generation,
        # Sprint 8.7: 性能统计(各阶段耗时 + cache 命中率)
        'performance': performance,
        'notes': (
            'Sprint 8.6: 已启用语义级评估(embedding 余弦相似度替代 Jaccard 表面 token 匹配)。'
            if sim_fn is not None else
            '本次使用规则级评估(无 ragas 依赖),指标为近似值, '
            '上线前可开启 use_llm_answer=True + LLM-as-a-Judge 获得更精确数值。'
        ),
    }
