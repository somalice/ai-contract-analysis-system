"""
Reranker 重排层(Sprint 8.6 - v1.0.0 RAG 质量优化)

职责:
- 对 DenseRetriever 召回的结果按 query-doc 相关性二次排序,提升 TopK 精度
- 解决向量检索"召回相关但排序不优"问题(FAISS 内积近似 + CrossEncoder 精排)

实现:
1. CrossEncoderReranker(主):基于 sentence_transformers.CrossEncoder
   - 复用 Embedding 已安装的 sentence_transformers(不新增依赖)
   - 模型 BAAI/bge-reranker-base(中文优化 cross-encoder)
   - 本地物化下载(与 Embedding 同策略,规避 Windows 符号链接问题)
   - 懒加载:首次调用触发下载
2. RuleBasedReranker(降级):基于 bigram Jaccard + 关键词覆盖率,零依赖
   - CrossEncoder import/加载失败时自动降级
3. get_reranker():读 config.RERANK_ENABLED,尝试 CrossEncoder → RuleBased → None

注入点:
- rag_service.query_rag(生产 RAG QA)
- run_rag_eval._retrieve_chunks(评估,确保评估观测到优化)
共用 rerank_results helper,保持两路径一致。

约束:
- rerank 失败不阻断业务:降级为原顺序前 final_k 条
- 不修改 DenseRetriever 契约(retrieve 仍返回按向量相似度降序的列表)
"""
import os
import re
from typing import List, Optional, Tuple

from app.extensions.logger import logger


# ============================================================
# 本地模型目录解析(与 Embedding 同策略,保持解耦)
# ============================================================
def _resolve_local_model_dir(model_name: str) -> str:
    """HF 模型名 → 本地物化目录 storage/models/<basename>/"""
    here = os.path.dirname(os.path.abspath(__file__))
    # backend/app/knowledge/rerank/ → 上 3 级 = backend
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    base_dir = os.path.join(backend_dir, 'storage', 'models')
    basename = model_name.rsplit('/', 1)[-1] if '/' in model_name else model_name
    return os.path.join(base_dir, basename)


# ============================================================
# CrossEncoder Reranker(主方案)
# ============================================================
class CrossEncoderReranker:
    """基于 sentence_transformers CrossEncoder 的精排器"""

    def __init__(self, model_name: str = 'BAAI/bge-reranker-base',
                 local_dir: str = None):
        self.model_name = model_name
        self.local_dir = local_dir or _resolve_local_model_dir(model_name)
        self._model = None

    def _ensure_local_model(self) -> str:
        """
        确保模型物化到本地;返回本地路径(与 Embedding 同策略)。

        Sprint 8.6 修复:仅检查 config.json 不足以判断模型完整性(可能只下载了
        tokenizer/config 而缺少权重文件)。必须同时检查 model.safetensors 或
        pytorch_model.bin 是否存在,否则 CrossEncoder 初始化会报
        "no file named model.safetensors, or pytorch_model.bin"。
        """
        config_path = os.path.join(self.local_dir, 'config.json')
        has_weights = (
            os.path.exists(os.path.join(self.local_dir, 'model.safetensors'))
            or os.path.exists(os.path.join(self.local_dir, 'pytorch_model.bin'))
        )
        if os.path.exists(config_path) and has_weights:
            return self.local_dir
        # 权重缺失:清理不完整目录后重新下载(避免 snapshot_download 跳过已存在文件)
        if os.path.exists(config_path) and not has_weights:
            logger.warning('[Knowledge:rerank] 检测到不完整模型目录(缺少权重文件),清理后重新下载: %s',
                           self.local_dir)
            import shutil
            try:
                shutil.rmtree(self.local_dir)
            except OSError:
                pass
        try:
            from huggingface_hub import snapshot_download
        except ImportError as e:
            raise ImportError('huggingface_hub 未安装,无法下载 reranker 模型') from e
        os.makedirs(self.local_dir, exist_ok=True)
        logger.info('[Knowledge:rerank] 首次下载 reranker 模型: %s → %s(可能较慢)',
                    self.model_name, self.local_dir)
        snapshot_download(repo_id=self.model_name, local_dir=self.local_dir)
        return self.local_dir

    @property
    def model(self):
        """懒加载 CrossEncoder(首次访问触发下载)"""
        if self._model is None:
            from sentence_transformers import CrossEncoder
            local_path = self._ensure_local_model()
            logger.info('[Knowledge:rerank] 加载 CrossEncoder: %s', local_path)
            self._model = CrossEncoder(local_path)
        return self._model

    def rerank(self, query: str, documents: List[str],
               top_k: int = 5) -> List[Tuple[int, float]]:
        """
        对 documents 按 (query, doc) 相关性排序

        :param query: 查询文本
        :param documents: 候选文档文本列表
        :param top_k: 返回前 K 条
        :return: [(original_index, score)] 按 score 降序,top_k 条
        :raises: Exception(由调用方降级)
        """
        if not documents:
            return []
        pairs = [(query, doc) for doc in documents]
        scores = self.model.predict(pairs, show_progress_bar=False)
        # 按 score 降序,返回 (原索引, 分数)
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: float(x[1]), reverse=True)
        return [(i, float(s)) for i, s in indexed[:top_k]]


# ============================================================
# Rule-Based Reranker(轻量降级方案,零依赖)
# ============================================================
_CJK_PUNCT = set('，。、；：？！“”‘’（）《》【】…—·,.!?;:"\'()[]<>')


def _tokenize(text: str) -> set:
    """极简中文分词(2-gram + 单字),用于规则打分"""
    if not text:
        return set()
    cleaned = ''.join(' ' if c in _CJK_PUNCT else c for c in text)
    tokens = set()
    for seg in re.split(r'\s+', cleaned):
        if re.match(r'^[A-Za-z0-9_]+$', seg):
            tokens.add(seg.lower())
        else:
            for i in range(max(0, len(seg) - 1)):
                bi = seg[i:i + 2]
                if not any(c.isspace() for c in bi):
                    tokens.add(bi)
    return tokens


class RuleBasedReranker:
    """基于 bigram Jaccard 的规则重排(CrossEncoder 不可用时降级)"""

    def rerank(self, query: str, documents: List[str],
               top_k: int = 5) -> List[Tuple[int, float]]:
        if not documents:
            return []
        q_tokens = _tokenize(query)
        scored = []
        for idx, doc in enumerate(documents):
            d_tokens = _tokenize(doc)
            if not q_tokens or not d_tokens:
                score = 0.0
            else:
                inter = len(q_tokens & d_tokens)
                union = len(q_tokens | d_tokens)
                score = inter / union if union > 0 else 0.0
            scored.append((idx, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


# ============================================================
# 工厂 + 高层入口
# ============================================================
# Sprint 8.6: 模块级缓存 reranker 实例,避免每次调用重新加载模型(模型加载 ~5s)
_cached_reranker = None
_cached_reranker_key = None  # (enabled, model_name) 用于检测 config 变化


def get_reranker():
    """
    按 config 返回 reranker 实例(模块级缓存,避免重复加载模型)

    :return: CrossEncoderReranker / RuleBasedReranker / None
        - RERANK_ENABLED=False → None
        - CrossEncoder 加载失败 → RuleBasedReranker(降级,零依赖)
        - 全部失败 → None
    """
    global _cached_reranker, _cached_reranker_key

    try:
        from flask import current_app
        enabled = current_app.config.get('RERANK_ENABLED', False)
        model_name = current_app.config.get('RERANKER_MODEL', 'BAAI/bge-reranker-base')
    except Exception:
        enabled = False
        model_name = 'BAAI/bge-reranker-base'

    if not enabled:
        return None

    # 缓存命中:同一 config 直接复用(避免每次调用重新加载 CrossEncoder 模型)
    cache_key = (enabled, model_name)
    if _cached_reranker is not None and _cached_reranker_key == cache_key:
        return _cached_reranker

    # 尝试 CrossEncoder(首次会触发模型下载)
    try:
        reranker = CrossEncoderReranker(model_name=model_name)
        # 预加载模型(触发下载/加载,失败则降级)
        _ = reranker.model
        _cached_reranker = reranker
        _cached_reranker_key = cache_key
        logger.info('[Knowledge:rerank] CrossEncoder 已缓存: %s', model_name)
        return reranker
    except Exception as e:
        logger.warning('[Knowledge:rerank] CrossEncoderReranker 初始化失败,降级 RuleBased: %s', e)
        try:
            reranker = RuleBasedReranker()
            _cached_reranker = reranker
            _cached_reranker_key = cache_key
            return reranker
        except Exception as e2:
            logger.warning('[Knowledge:rerank] RuleBasedReranker 初始化失败,禁用 rerank: %s', e2)
            return None


def rerank_results(query: str,
                   retrieval_results: list,
                   final_k: int = 5,
                   db_session=None,
                   KnowledgeChunk=None) -> list:
    """
    对检索结果重排的高层入口(供 rag_service / run_rag_eval 复用)

    :param query: 查询文本
    :param retrieval_results: list[RetrievalResult](原顺序,按向量相似度降序)
    :param final_k: 最终返回条数
    :param db_session: SQLAlchemy session(用于查 chunk 文本)
    :param KnowledgeChunk: KnowledgeChunk 模型类
    :return: list[RetrievalResult] 重排后前 final_k 条
        - reranker=None / 异常 / 无 db → 原顺序前 final_k 条(零风险降级)
    """
    if not retrieval_results:
        return retrieval_results
    # 无需重排:结果数 <= final_k 且 rerank 关闭时直接截断
    reranker = get_reranker()
    if reranker is None:
        return retrieval_results[:final_k]

    # 需要 chunk 文本来打分
    if db_session is None or KnowledgeChunk is None:
        logger.warning('[Knowledge:rerank] 缺少 db_session/KnowledgeChunk,跳过 rerank')
        return retrieval_results[:final_k]

    try:
        chunk_ids = [r.chunk_id for r in retrieval_results if r.chunk_id]
        if not chunk_ids:
            return retrieval_results[:final_k]
        chunks = (
            db_session.query(KnowledgeChunk)
            .filter(KnowledgeChunk.id.in_(chunk_ids))
            .all()
        )
        id_to_text = {c.id: (c.text or '') for c in chunks}
        documents = [id_to_text.get(r.chunk_id, '') for r in retrieval_results]

        ranked = reranker.rerank(query, documents, top_k=final_k)
        # ranked = [(orig_idx, score)],按新顺序取对应 retrieval_results
        return [retrieval_results[i] for i, _ in ranked]
    except Exception as e:
        # Sprint 8.6: CrossEncoder 失败(如模型下载失败/加载超时)→ 降级 RuleBasedReranker
        logger.warning('[Knowledge:rerank] %s rerank 失败,尝试 RuleBasedReranker 降级: %s',
                       type(reranker).__name__, e)
        try:
            rule_reranker = RuleBasedReranker()
            ranked = rule_reranker.rerank(query, documents, top_k=final_k)
            logger.info('[Knowledge:rerank] RuleBasedReranker 降级成功')
            return [retrieval_results[i] for i, _ in ranked]
        except Exception as e2:
            logger.warning('[Knowledge:rerank] RuleBasedReranker 也失败,使用原顺序: %s', e2)
            return retrieval_results[:final_k]
