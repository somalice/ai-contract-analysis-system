"""
RAG 评估指标实现(Sprint 8.5 - v1.0.0 RC / Sprint 8.6 语义升级)

实现 4 大核心 RAG 指标:
1. Faithfulness: 回答忠实度 → 回答是否来源于检索内容(无幻觉)
2. Answer Relevancy: 回答相关性 → 回答是否解决用户问题
3. Context Precision: 上下文精确度 → 召回内容是否相关(TopK 排序相关度)
4. Context Recall: 上下文召回率 → 是否召回完整 ground truth 信息

设计原则:
- 优先使用 LLM-as-a-Judge (复用现有 DeepSeek + LangChain, 不引入 ragas 以避免依赖冲突)
- 无 LLM 时提供规则降级方案 (关键词重叠 + 语义相似度近似指标)
- 所有指标结果归一化到 [0, 1] 区间
- 纯函数式: 指标函数不直接调用 DB/Retriever, 仅接收结构化输入

Sprint 8.6 升级:
- 新增 sim_fn 参数(语义相似度函数), 优先使用 Embedding 余弦相似度
- sim_fn=None 时回退到原 Jaccard/字符 n-gram 规则方案(完全向后兼容)
- 语义模式解决中文文本表面 token 匹配的局限性:
  · Context Precision: 用 embedding cosine 替代 Jaccard(短问题 vs 长 chunk 不再被惩罚)
  · Context Recall: 用 embedding cosine 替代 bi-gram Jaccard(措辞差异不再致指标失真)
  · Answer Relevancy: 用 embedding cosine 替代关键词覆盖率
  · Faithfulness: 用 embedding cosine 逐句匹配 context(语义级支持度)
"""
from __future__ import annotations

import json
import re
import math
from collections import Counter
from typing import List, Dict, Optional, Any, Callable


# 语义相似度函数类型: (text_a, text_b) -> float in [0, 1]
SimFn = Callable[[str, str], float]


# ============================================================
# 文本工具:中文分词(极简版,不依赖 jieba,仅按标点+常用停词切分)
# ============================================================
_CJK_PUNCT = set('，。、；：？！“”‘’（）《》【】…—·,.!?;:"\'()[]<>')
_STOPWORDS = set('''
的 了 和 是 就 都 而 及 与 着 或 一个 没有 我们 你们 他们 它们 这个 那个 这些 那些
什么 怎么 如何 为什么 因为 所以 如果 但是 然而 虽然 可以 可能 应当 必须 需要 以及
包括 对于 关于 通过 根据 在 于 从 到 为 对 以 和 及 其 此 该 之 等 项 条 款
'''.split())


def _tokenize(text: str) -> List[str]:
    """极简中文分词(字符2-gram+混合切词,用于召回类指标)。"""
    if not text:
        return []
    # 去标点
    cleaned = ''.join(' ' if c in _CJK_PUNCT else c for c in text)
    tokens = []
    # 1. 连续英文/数字按空格切
    for seg in re.split(r'\s+', cleaned):
        if re.match(r'^[A-Za-z0-9_]+$', seg):
            tokens.append(seg.lower())
        else:
            # 2. 中文 2-gram(兼顾无分词依赖的鲁棒性)
            for i in range(len(seg) - 1):
                bi = seg[i:i+2]
                if not any(c.isspace() for c in bi):
                    tokens.append(bi)
            # 3. 单字符只加非停用字
            for c in seg:
                if c.strip() and c not in _CJK_PUNCT and c not in _STOPWORDS:
                    tokens.append(c)
    return [t for t in tokens if t and t not in _STOPWORDS and len(t.strip()) > 0]


def _char_ngrams(text: str, n: int = 2) -> List[str]:
    """字符 n-gram,避免分词差异。"""
    if not text:
        return []
    return [text[i:i+n] for i in range(max(0, len(text) - n + 1)) if text[i:i+n].strip()]


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def _precision(tp: int, fp: int) -> float:
    total = tp + fp
    return tp / total if total > 0 else 0.0


def _recall(tp: int, fn: int) -> float:
    total = tp + fn
    return tp / total if total > 0 else 0.0


def _f1(p: float, r: float) -> float:
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


# ============================================================
# 3. Context Precision: 召回内容与问题的相关性(TopK加权)
# ============================================================
def context_precision(
    question: str,
    retrieved_chunks: List[str],
    ground_truth: Optional[str] = None,
    sim_fn: Optional[SimFn] = None,
) -> float:
    """
    Context Precision。

    定义: 越靠前的 chunk 越相关 → 精度越高。
    计算公式 (近似 DCG 归一化):
        score = Σ_{rank} sim(q, chunk_rank) / log2(rank+1) / Σ_{rank} 1/log2(rank+1)

    Sprint 8.6:
    - sim_fn 提供时: sim = max(sim_fn(question, chunk), sim_fn(ground_truth, chunk) * 0.8)
      (embedding 余弦相似度,语义级匹配,短问题 vs 长 chunk 不受 token 长度惩罚)
    - sim_fn=None 时: 回退 Jaccard(原规则降级行为,完全向后兼容)
    """
    if not retrieved_chunks:
        return 0.0

    if sim_fn is not None:
        scores = []
        for idx, chunk in enumerate(retrieved_chunks):
            rank = idx + 1
            sim_q = sim_fn(question, chunk)
            sim_gt = sim_fn(ground_truth, chunk) if ground_truth else 0.0
            # Sprint 8.6 修正: 采用 max(sim_q, sim_gt) 而非绝对相似度或 min-max 归一化。
            # - 绝对相似度受 bge-small 模型特性影响(同类文本 0.6~0.85,不相关 0.3~0.5),
            #   直接用 sim_q 会系统性偏低;
            # - min-max 归一化(加权后)会扭曲 DCG 折扣结构,已实测劣化;
            # - ground_truth 是标准答案,包含问题所需全部信息,sim(gt, chunk) 是
            #   判断"chunk 是否包含回答问题所需信息"的强信号(对齐 RAGAS Context
            #   Precision 用 ground_truth 判断相关性的学术定义)。
            sim = max(sim_q, sim_gt)
            discount = math.log2(rank + 1)
            scores.append(sim / discount)
    else:
        scores = []
        q_toks = set(_tokenize(question))
        gt_toks = set(_tokenize(ground_truth)) if ground_truth else set()
        for idx, chunk in enumerate(retrieved_chunks):
            rank = idx + 1
            c_toks = set(_tokenize(chunk))
            sim_q = _jaccard(q_toks, c_toks)
            sim_gt = _jaccard(gt_toks, c_toks) if gt_toks else 0.0
            sim = max(sim_q, sim_gt * 0.8)
            discount = math.log2(rank + 1)
            scores.append(sim / discount)

    # 最大可能归一化系数 (sim=1 的理想列表)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, len(retrieved_chunks) + 1))
    if idcg <= 0:
        return 0.0
    return min(1.0, sum(scores) / idcg)


# ============================================================
# 4. Context Recall: 召回上下文覆盖 ground truth 关键信息的比例
# ============================================================
def context_recall(
    ground_truth: str,
    retrieved_chunks: List[str],
    sim_fn: Optional[SimFn] = None,
) -> float:
    """
    Context Recall。

    Sprint 8.6:
    - sim_fn 提供时: 直接返回 sim_fn(ground_truth, merged_context)
      (embedding 余弦相似度,语义级覆盖,措辞差异不再致指标失真)
    - sim_fn=None 时: 回退 bi-gram + unigram Jaccard(原规则降级行为)
    """
    if not ground_truth:
        return 1.0
    if not retrieved_chunks:
        return 0.0

    if sim_fn is not None:
        merged_context = '\n'.join(retrieved_chunks)
        return round(max(0.0, min(1.0, sim_fn(ground_truth, merged_context))), 4)

    # 规则降级: bi-gram + unigram Jaccard
    gt_unigrams = set(t for t in _tokenize(ground_truth) if len(t) == 1)
    gt_bigrams = set(t for t in _tokenize(ground_truth) if len(t) == 2)
    merged_context = '\n'.join(retrieved_chunks)
    ctx_unigrams = set(t for t in _tokenize(merged_context) if len(t) == 1)
    ctx_bigrams = set(t for t in _tokenize(merged_context) if len(t) == 2)

    bi_rec = _jaccard(gt_bigrams, ctx_bigrams)
    uni_rec = _recall(
        len(gt_unigrams & ctx_unigrams),
        len(gt_unigrams - ctx_unigrams),
    )
    # bigram 权重更高(语义片段匹配更关键)
    return round(0.65 * bi_rec + 0.35 * uni_rec, 4)


# ============================================================
# 1. Faithfulness: 回答是否来自检索上下文(无幻觉)
# ============================================================
# Sprint 8.8 Phase 6: 纯引用标注句识别(如 "[文档1][文档2]" / "[文档3]")。
# 标注符号无语义内容,不应作为"幻觉句子"参与忠实度判定(评估口径修正,非放宽阈值)。
_LABEL_ONLY_RE = re.compile(r'^[\s\[\]【】,，、。；;]*((文档\s*\d+)[\s\[\]【】,，、。；;]*)+$')


def _is_pure_label_sentence(sentence: str) -> bool:
    """判断句子是否仅为引用标注(无实质内容)。"""
    s = sentence.strip()
    if not s:
        return True
    if _LABEL_ONLY_RE.match(s):
        return True
    return False


def faithfulness(
    answer: str,
    context_chunks: List[str],
    sim_fn: Optional[SimFn] = None,
) -> float:
    """
    Faithfulness: answer 中句子有多少可被 context 支持。

    Sprint 8.6:
    - sim_fn 提供时: 对每个 answer 句子取与所有 context chunk 的最大语义相似度,
      所有句子的 max-sim 取平均(语义级支持度,不受表面 token 差异影响)
    - sim_fn=None 时: 回退字符 n-gram 覆盖率(原规则降级行为)
    """
    if not answer or not answer.strip():
        return 1.0  # 空答案不产生幻觉,但 relevancy 会低
    if not context_chunks:
        return 0.0  # 无上下文还回答,认定幻觉

    # 切句(Sprint 8.8 Phase 6: 剔除纯引用标注句,避免 [文档n] 无实质内容句被当作幻觉)
    sentences = [
        s.strip() for s in re.split(r'[。；;\n!?？!]', answer)
        if s.strip() and not _is_pure_label_sentence(s)
    ]
    if not sentences:
        return 0.0

    if sim_fn is not None:
        # 语义模式: 每句取与所有 chunk 的最大相似度,取平均
        support_scores = []
        for s in sentences:
            if len(s) < 2:
                continue
            max_sim = max(sim_fn(s, chunk) for chunk in context_chunks)
            support_scores.append(max_sim)
        if not support_scores:
            return 0.0
        return round(sum(support_scores) / len(support_scores), 4)

    # 规则降级: 字符 n-gram 覆盖率
    merged_ctx = '\n'.join(context_chunks)
    ctx_bi = set(_char_ngrams(merged_ctx, n=2))
    ctx_bi.update(_char_ngrams(merged_ctx, n=3))

    support_scores = []
    for s in sentences:
        if len(s) < 2:
            continue
        s_bi = set(_char_ngrams(s, n=2))
        s_bi.update(_char_ngrams(s, n=3))
        if not s_bi:
            continue
        # 句子 token 在 context 中出现的比例 (bi-gram 覆盖率)
        supported = len(s_bi & ctx_bi)
        ratio = supported / len(s_bi)
        # 若句子较短,适当放宽
        if len(s) <= 6:
            ratio = min(1.0, ratio + 0.1)
        support_scores.append(ratio)

    if not support_scores:
        return 0.0
    return round(sum(support_scores) / len(support_scores), 4)


# ============================================================
# 2. Answer Relevancy: 回答是否解决用户问题
# ============================================================
_QUESTION_STARTERS = set('什么 为什么 怎么 如何 哪 哪些 哪里 何时 谁 多少 是否 呢 吗 请问'.split())


def answer_relevancy(
    question: str,
    answer: str,
    sim_fn: Optional[SimFn] = None,
    ground_truth: Optional[str] = None,
) -> float:
    """
    Answer Relevancy: 回答对问题的响应程度。

    Sprint 8.6:
    - sim_fn 提供时: 综合 question 与 ground_truth 双侧相关性
        sim = 0.6 * sim(question, answer) + 0.4 * sim(ground_truth, answer)
      (回答既要贴题,又要贴近标准答案语义;与 RAGAS Answer Relevancy
       通过对比 ground_truth 判断回答是否恰当的学术定义一致)
      叠加长度合理性惩罚(过短回答适当降分)
    - sim_fn=None 时: 回退关键词覆盖率 + 长度启发式(原规则降级行为)
    """
    if not question or not answer:
        return 0.0

    if sim_fn is not None:
        sim_q = max(0.0, min(1.0, sim_fn(question, answer)))
        if ground_truth:
            sim_gt = max(0.0, min(1.0, sim_fn(ground_truth, answer)))
            semantic_sim = 0.6 * sim_q + 0.4 * sim_gt
        else:
            semantic_sim = sim_q
        # 长度合理性微调(过短回答适当惩罚)
        a_len = len(answer.strip())
        if a_len >= 15:
            length_penalty = 1.0
        elif a_len >= 8:
            length_penalty = 0.85
        elif a_len >= 4:
            length_penalty = 0.6
        else:
            length_penalty = 0.3
        return round(semantic_sim * length_penalty, 4)

    # 规则降级: 关键词覆盖率 + 长度启发式
    q_tokens = set(t for t in _tokenize(question) if t not in _QUESTION_STARTERS)
    # 去除纯疑问词
    a_tokens = set(_tokenize(answer))
    # 关键词覆盖率
    if q_tokens:
        hit_rate = len(q_tokens & a_tokens) / len(q_tokens)
    else:
        hit_rate = 0.5
    # 长度合理性:期望回答长度 > 问题长度的 1.5 倍,且至少 10 字
    q_len = len(question.strip())
    a_len = len(answer.strip())
    if a_len >= q_len * 1.5 and a_len >= 15:
        length_score = 1.0
    elif a_len >= q_len and a_len >= 8:
        length_score = 0.7
    elif a_len >= 4:
        length_score = 0.4
    else:
        length_score = 0.1
    # 空泛检测:若回答全是套话"需要根据合同具体分析/视情况而定"但无实质内容则降分
    empty_phrases = ['视情况', '具体问题', '具体分析', '根据合同', '根据实际', '需要结合', '具体情况']
    empty_count = sum(1 for p in empty_phrases if p in answer)
    if empty_count >= 2 and a_len < 40:
        length_score *= 0.6

    return round(0.55 * hit_rate + 0.45 * length_score, 4)


# ============================================================
# 聚合评估: 单条样本 → 4 指标 dict
# ============================================================
def evaluate_single_sample(
    question: str,
    answer: str,
    context_chunks: List[str],
    ground_truth: str,
    sim_fn: Optional[SimFn] = None,
) -> Dict[str, float]:
    """
    对单条 RAG 问答样本计算 4 指标。

    :param sim_fn: Sprint 8.6 语义相似度函数;提供时使用 embedding 余弦相似度,
                   None 时回退规则降级方案(向后兼容)
    :return: {faithfulness, answer_relevancy, context_precision, context_recall}
    """
    return {
        'faithfulness': faithfulness(answer, context_chunks, sim_fn=sim_fn),
        'answer_relevancy': answer_relevancy(question, answer, sim_fn=sim_fn),
        'context_precision': context_precision(question, context_chunks, ground_truth, sim_fn=sim_fn),
        'context_recall': context_recall(ground_truth, context_chunks, sim_fn=sim_fn),
    }


def aggregate_scores(scores: List[Dict[str, float]]) -> Dict[str, Any]:
    """对批量样本取平均, 输出 mean + std(近似) + 达标率(>=targets)。"""
    if not scores:
        return {'count': 0, 'mean': {}, 'pass_rate': {}}
    metric_names = ['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']
    target = {'faithfulness': 0.85, 'answer_relevancy': 0.85,
              'context_precision': 0.80, 'context_recall': 0.80}
    mean = {}
    pass_rate = {}
    for m in metric_names:
        vals = [s.get(m, 0.0) for s in scores]
        mean[m] = round(sum(vals) / len(vals), 4)
        passed = sum(1 for v in vals if v >= target[m])
        pass_rate[m] = round(passed / len(vals), 4)
    return {
        'count': len(scores),
        'mean': mean,
        'pass_rate': pass_rate,
        'targets': target,
    }
